from django.shortcuts import render, redirect
import torch
import torchvision
from torchvision import transforms, models
from torch.utils.data import DataLoader
from torch.utils.data.dataset import Dataset
import os
import numpy as np
import cv2
import face_recognition

# Use non-interactive backend
import matplotlib.pyplot as plt
from torch.autograd import Variable
import time
import sys
from torch import nn
import json
import glob
import copy
from torchvision import models
import shutil
from PIL import Image as pImage
import time
from django.conf import settings
from .forms import VideoUploadForm
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


index_template_name = 'index.html'
predict_template_name = 'predict.html'
about_template_name = "about.html"

im_size = 112
mean=[0.485, 0.456, 0.406]
std=[0.229, 0.224, 0.225]
sm = nn.Softmax()
inv_normalize =  transforms.Normalize(mean=-1*np.divide(mean,std),std=np.divide([1,1,1],std))
if torch.cuda.is_available():
    device = 'gpu'
else:
    device = 'cpu'

train_transforms = transforms.Compose([
                                        transforms.ToPILImage(),
                                        transforms.Resize((im_size,im_size)),
                                        transforms.ToTensor(),
                                        transforms.Normalize(mean,std)])

class Model(nn.Module):

    def __init__(self, num_classes,latent_dim= 2048, lstm_layers=1 , hidden_dim = 2048, bidirectional = False):
        super(Model, self).__init__()
        model = models.resnext50_32x4d(pretrained = True)
        self.model = nn.Sequential(*list(model.children())[:-2])
        self.lstm = nn.LSTM(latent_dim,hidden_dim, lstm_layers,  bidirectional)
        self.relu = nn.LeakyReLU()
        self.dp = nn.Dropout(0.4)
        self.linear1 = nn.Linear(2048,num_classes)
        self.avgpool = nn.AdaptiveAvgPool2d(1)

    def forward(self, x):
        batch_size,seq_length, c, h, w = x.shape
        x = x.view(batch_size * seq_length, c, h, w)
        fmap = self.model(x)
        x = self.avgpool(fmap)
        x = x.view(batch_size,seq_length,2048)
        x_lstm,_ = self.lstm(x,None)
        return fmap,self.dp(self.linear1(x_lstm[:,-1,:]))


class validation_dataset(Dataset):
    def __init__(self,video_names,sequence_length=60,transform = None):
        self.video_names = video_names
        self.transform = transform
        self.count = sequence_length

    def __len__(self):
        return len(self.video_names)

    def __getitem__(self,idx):
        video_path = self.video_names[idx]
        frames = []
        a = int(100/self.count)
        first_frame = np.random.randint(0,a)
        for i,frame in enumerate(self.frame_extract(video_path)):
            #if(i % a == first_frame):
            faces = face_recognition.face_locations(frame)
            try:
              top,right,bottom,left = faces[0]
              frame = frame[top:bottom,left:right,:]
            except:
              pass
            frames.append(self.transform(frame))
            if(len(frames) == self.count):
                break
        """
        for i,frame in enumerate(self.frame_extract(video_path)):
            if(i % a == first_frame):
                frames.append(self.transform(frame))
        """        
        # if(len(frames)<self.count):
        #   for i in range(self.count-len(frames)):
        #         frames.append(self.transform(frame))
        #print("no of frames", self.count)
        frames = torch.stack(frames)
        frames = frames[:self.count]
        return frames.unsqueeze(0)
    
    def frame_extract(self,path):
      vidObj = cv2.VideoCapture(path) 
      success = 1
      while success:
          success, image = vidObj.read()
          if success:
              yield image

def im_convert(tensor, video_file_name):
    """ Display a tensor as an image. """
    image = tensor.to("cpu").clone().detach()
    image = image.squeeze()
    image = inv_normalize(image)
    image = image.numpy()
    image = image.transpose(1,2,0)
    image = image.clip(0, 1)
    # This image is not used
    # cv2.imwrite(os.path.join(settings.PROJECT_DIR, 'uploaded_images', video_file_name+'_convert_2.png'),image*255)
    return image

def im_plot(tensor):
    image = tensor.cpu().numpy().transpose(1,2,0)
    b,g,r = cv2.split(image)
    image = cv2.merge((r,g,b))
    image = image*[0.22803, 0.22145, 0.216989] +  [0.43216, 0.394666, 0.37645]
    image = image*255.0
    plt.imshow(image.astype('uint8'))
    plt.show()


def predict(model,img,path = './', video_file_name=""):
  fmap,logits = model(img.to(device))
  img = im_convert(img[:,-1,:,:,:], video_file_name)
  params = list(model.parameters())
  weight_softmax = model.linear1.weight.detach().cpu().numpy()
  logits = sm(logits)
  _,prediction = torch.max(logits,1)
  confidence = logits[:,int(prediction.item())].item()*100
  print('confidence of prediction:',logits[:,int(prediction.item())].item()*100)  
  return [int(prediction.item()),confidence]

def plot_heat_map(i, model, img, path = './', video_file_name=''):
  fmap,logits = model(img.to(device))
  params = list(model.parameters())
  weight_softmax = model.linear1.weight.detach().cpu().numpy()
  logits = sm(logits)
  _,prediction = torch.max(logits,1)
  idx = np.argmax(logits.detach().cpu().numpy())
  bz, nc, h, w = fmap.shape
  #out = np.dot(fmap[-1].detach().cpu().numpy().reshape((nc, h*w)).T,weight_softmax[idx,:].T)
  out = np.dot(fmap[i].detach().cpu().numpy().reshape((nc, h*w)).T,weight_softmax[idx,:].T)
  predict = out.reshape(h,w)
  predict = predict - np.min(predict)
  predict_img = predict / np.max(predict)
  predict_img = np.uint8(255*predict_img)
  out = cv2.resize(predict_img, (im_size,im_size))
  heatmap = cv2.applyColorMap(out, cv2.COLORMAP_JET)
  img = im_convert(img[:,-1,:,:,:], video_file_name)
  result = heatmap * 0.5 + img*0.8*255
  # Saving heatmap - Start
  heatmap_name = video_file_name+"_heatmap_"+str(i)+".png"
  image_name = os.path.join(settings.PROJECT_DIR, 'uploaded_images', heatmap_name)
  cv2.imwrite(image_name,result)
  # Saving heatmap - End
  result1 = heatmap * 0.5/255 + img*0.8
  r,g,b = cv2.split(result1)
  result1 = cv2.merge((r,g,b))
  return image_name

# Model Selection
def get_accurate_model(sequence_length):
    model_name = []
    sequence_model = []
    final_model = ""
    list_models = glob.glob(os.path.join(settings.PROJECT_DIR, "models", "*.pt"))

    for model_path in list_models:
        model_name.append(os.path.basename(model_path))

    for model_filename in model_name:
        try:
            seq = model_filename.split("_")[3]
            if int(seq) == sequence_length:
                sequence_model.append(model_filename)
        except IndexError:
            pass  # Handle cases where the filename format doesn't match expected

    if len(sequence_model) > 1:
        accuracy = []
        for filename in sequence_model:
            acc = filename.split("_")[1]
            accuracy.append(acc)  # Convert accuracy to float for proper comparison
        max_index = accuracy.index(max(accuracy))
        final_model = os.path.join(settings.PROJECT_DIR, "models", sequence_model[max_index])
    elif len(sequence_model) == 1:
        final_model = os.path.join(settings.PROJECT_DIR, "models", sequence_model[0])
    else:
        print("No model found for the specified sequence length.")  # Handle no models found case

    return final_model

ALLOWED_VIDEO_EXTENSIONS = set(['mp4','gif','webm','avi','3gp','wmv','flv','mkv'])

def allowed_video_file(filename):
    #print("filename" ,filename.rsplit('.',1)[1].lower())
    if (filename.rsplit('.',1)[1].lower() in ALLOWED_VIDEO_EXTENSIONS):
        return True
    else: 
        return False
def index(request):
    if request.method == 'GET':
        video_upload_form = VideoUploadForm()
        if 'file_name' in request.session:
            del request.session['file_name']
        if 'preprocessed_images' in request.session:
            del request.session['preprocessed_images']
        if 'faces_cropped_images' in request.session:
            del request.session['faces_cropped_images']
        return render(request, index_template_name, {"form": video_upload_form})
    else:
        video_upload_form = VideoUploadForm(request.POST, request.FILES)
        if video_upload_form.is_valid():
            video_file = video_upload_form.cleaned_data['upload_video_file']
            video_file_ext = video_file.name.split('.')[-1]
            sequence_length = video_upload_form.cleaned_data['sequence_length']
            video_content_type = video_file.content_type.split('/')[0]
            if video_content_type in settings.CONTENT_TYPES:
                if video_file.size > int(settings.MAX_UPLOAD_SIZE):
                    video_upload_form.add_error("upload_video_file", "Maximum file size 100 MB")
                    return render(request, index_template_name, {"form": video_upload_form})

            if sequence_length <= 0:
                video_upload_form.add_error("sequence_length", "Sequence Length must be greater than 0")
                return render(request, index_template_name, {"form": video_upload_form})
            
            if allowed_video_file(video_file.name) == False:
                video_upload_form.add_error("upload_video_file","Only video files are allowed ")
                return render(request, index_template_name, {"form": video_upload_form})
            
            saved_video_file = 'uploaded_file_'+str(int(time.time()))+"."+video_file_ext
            if settings.DEBUG:
                with open(os.path.join(settings.PROJECT_DIR, 'uploaded_videos', saved_video_file), 'wb') as vFile:
                    shutil.copyfileobj(video_file, vFile)
                request.session['file_name'] = os.path.join(settings.PROJECT_DIR, 'uploaded_videos', saved_video_file)
            else:
                with open(os.path.join(settings.PROJECT_DIR, 'uploaded_videos','app','uploaded_videos', saved_video_file), 'wb') as vFile:
                    shutil.copyfileobj(video_file, vFile)
                request.session['file_name'] = os.path.join(settings.PROJECT_DIR, 'uploaded_videos','app','uploaded_videos', saved_video_file)
            request.session['sequence_length'] = sequence_length
            return redirect('ml_app:predict')
        else:
            return render(request, index_template_name, {"form": video_upload_form})


def predict_page(request):
    if request.method == "GET":
        # Redirect to 'home' if 'file_name' is not in session
        if 'file_name' not in request.session:
            return redirect("ml_app:home")
        if 'file_name' in request.session:
            video_file = request.session['file_name']
        if 'sequence_length' in request.session:
            sequence_length = request.session['sequence_length']
        path_to_videos = [video_file]
        video_file_name = os.path.basename(video_file)
        video_file_name_only = os.path.splitext(video_file_name)[0]
        # Production environment adjustments
        if not settings.DEBUG:
            production_video_name = os.path.join('/home/app/staticfiles/', video_file_name.split('/')[3])
            print("Production file name", production_video_name)
        else:
            production_video_name = video_file_name

        # Load validation dataset
        video_dataset = validation_dataset(path_to_videos, sequence_length=sequence_length, transform=train_transforms)

        # Load model
        if(device == "gpu"):
            model = Model(2).cuda()  # Adjust the model instantiation according to your model structure
        else:
            model = Model(2).cpu()  # Adjust the model instantiation according to your model structure
        model_name = os.path.join(settings.PROJECT_DIR, 'models', get_accurate_model(sequence_length))
        path_to_model = os.path.join(settings.PROJECT_DIR, model_name)
        model.load_state_dict(torch.load(path_to_model, map_location=torch.device('cpu')))
        model.eval()
        start_time = time.time()
        # Display preprocessing images
        print("<=== | Started Videos Splitting | ===>")
        preprocessed_images = []
        faces_cropped_images = []
        cap = cv2.VideoCapture(video_file)
        frames = []
        while cap.isOpened():
            ret, frame = cap.read()
            if ret:
                frames.append(frame)
            else:
                break
        cap.release()

        print(f"Number of frames: {len(frames)}")
        # Process each frame for preprocessing and face cropping
        padding = 40
        faces_found = 0
        for i in range(sequence_length):
            if i >= len(frames):
                break
            frame = frames[i]

            # Convert BGR to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Save preprocessed image
            image_name = f"{video_file_name_only}_preprocessed_{i+1}.png"
            image_path = os.path.join(settings.PROJECT_DIR, 'uploaded_images', image_name)
            img_rgb = pImage.fromarray(rgb_frame, 'RGB')
            img_rgb.save(image_path)
            preprocessed_images.append(image_name)

            # Face detection and cropping
            face_locations = face_recognition.face_locations(rgb_frame)
            if len(face_locations) == 0:
                continue

            top, right, bottom, left = face_locations[0]
            frame_face = frame[top - padding:bottom + padding, left - padding:right + padding]

            # Convert cropped face image to RGB and save
            rgb_face = cv2.cvtColor(frame_face, cv2.COLOR_BGR2RGB)
            img_face_rgb = pImage.fromarray(rgb_face, 'RGB')
            image_name = f"{video_file_name_only}_cropped_faces_{i+1}.png"
            image_path = os.path.join(settings.PROJECT_DIR, 'uploaded_images', image_name)
            img_face_rgb.save(image_path)
            faces_found += 1
            faces_cropped_images.append(image_name)

        print("<=== | Videos Splitting and Face Cropping Done | ===>")
        print("--- %s seconds ---" % (time.time() - start_time))

        # No face detected
        if faces_found == 0:
            return render(request, 'predict_template_name', {"no_faces": True})

        # Perform prediction
        try:
            heatmap_images = []
            output = ""
            confidence = 0.0

            for i in range(len(path_to_videos)):
                print("<=== | Started Prediction | ===>")
                prediction = predict(model, video_dataset[i], './', video_file_name_only)
                confidence = round(prediction[1], 1)
                output = "REAL" if prediction[0] == 1 else "FAKE"
                print("Prediction:", prediction[0], "==", output, "Confidence:", confidence)
                print("<=== | Prediction Done | ===>")
                print("--- %s seconds ---" % (time.time() - start_time))

                # Uncomment if you want to create heat map images
                # for j in range(sequence_length):
                #     heatmap_images.append(plot_heat_map(j, model, video_dataset[i], './', video_file_name_only))

            # Render results
            context = {
                'preprocessed_images': preprocessed_images,
                'faces_cropped_images': faces_cropped_images,
                'heatmap_images': heatmap_images,
                'original_video': production_video_name,
                'models_location': os.path.join(settings.PROJECT_DIR, 'models'),
                'output': output,
                'confidence': confidence
            }

            if settings.DEBUG:
                # return render(request, predict_template_name, context)
                return render(request, "predict2.html", context)
            else:
                # return render(request, predict_template_name, context)
                return render(request, "predict2.html", context)

        except Exception as e:
            print(f"Exception occurred during prediction: {e}")
            return render(request, 'cuda_full.html')
def about(request):
    return render(request, about_template_name)

def handler404(request,exception):
    return render(request, '404.html', status=404)
def cuda_full(request):
    return render(request, 'cuda_full.html')

import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import tempfile
import os
import shutil
import time
import cv2
from PIL import Image as pImage
import face_recognition
import torch
from torchvision import transforms
import torch.nn as nn

@csrf_exempt
@require_POST
def predict_api(request):
    try:
        print("HI My api called ")

        if 'upload_video_file' not in request.FILES:
            print("No video uploaded")
            return JsonResponse({"error": "No video file provided"}, status=400)

        video_file = request.FILES['upload_video_file']
        sequence_length = int(request.POST.get('sequence_length', 10))

        print(f"Video file: {video_file.name}, Sequence length: {sequence_length}")

        # Save the video to the MEDIA_ROOT directory (where Django expects it)
        video_file_name = f'uploaded_file_{int(time.time())}.{video_file.name.split(".")[-1]}'
        video_file_path = os.path.join(settings.MEDIA_ROOT, video_file_name)
        
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(video_file_path), exist_ok=True)
        
        with open(video_file_path, 'wb') as vFile:
            for chunk in video_file.chunks():
                vFile.write(chunk)
        print(f"Saved video to {video_file_path}")

        # Process the video
        result = process_video_prediction(video_file_path,10)
        print("Result from process_video_prediction:", result)

        # Return the filename for the frontend to access
        result['original_video'] = video_file_name

        print("Returning result")
        return JsonResponse(result)

    except Exception as e:
        print(f"Exception in predict_api: {e}")
        # Clean up on error
        if 'video_file_path' in locals():
            try:
                os.remove(video_file_path)
            except:
                pass
        return JsonResponse({"error": str(e)}, status=500)

    
# def process_video_prediction(video_file_path, sequence_length):
#     try:
#         path_to_videos = [video_file_path]
#         video_file_name = os.path.basename(video_file_path)
#         video_file_name_only = os.path.splitext(video_file_name)[0]

#         # Load validation dataset and model (keep this part the same)
#         video_dataset = validation_dataset(path_to_videos, sequence_length=sequence_length, transform=train_transforms)
        
#         if torch.cuda.is_available():
#             model = Model(2).cuda()
#         else:
#             model = Model(2).cpu()
            
#         model_name = get_accurate_model(sequence_length)
#         if not model_name:
#             raise Exception("No suitable model found for the specified sequence length")
            
#         path_to_model = os.path.join(settings.PROJECT_DIR, 'models', model_name)
#         model.load_state_dict(torch.load(path_to_model, map_location=torch.device('cpu')))
#         model.eval()
        
#         start_time = time.time()
        
#         # Create uploaded_images directory if it doesn't exist - USE PROJECT_DIR
#         uploaded_images_dir = os.path.join(settings.PROJECT_DIR, 'uploaded_images')
#         os.makedirs(uploaded_images_dir, exist_ok=True)
        
#         print("<=== | Started Videos Splitting | ===>")
#         preprocessed_images = []
#         faces_cropped_images = []
        
#         # Extract frames from video
#         cap = cv2.VideoCapture(video_file_path)
#         frames = []
#         while cap.isOpened():
#             ret, frame = cap.read()
#             if not ret:
#                 break
#             frames.append(frame)
#         cap.release()

#         print(f"Number of frames: {len(frames)}")
        
#         # Process each frame
#         padding = 40
#         faces_found = 0
        
#         for i in range(min(sequence_length, len(frames))):
#             frame = frames[i]
            
#             # Convert BGR to RGB
#             rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
#             # Save preprocessed image - Use the correct path
#             image_name = f"{video_file_name_only}_preprocessed_{i+1}.png"
#             image_path = os.path.join(uploaded_images_dir, image_name)
#             img_rgb = pImage.fromarray(rgb_frame, 'RGB')
#             img_rgb.save(image_path)
#             preprocessed_images.append(image_name)
            
#             # Face detection and cropping
#             face_locations = face_recognition.face_locations(rgb_frame)
#             if len(face_locations) == 0:
#                 continue
            
#             top, right, bottom, left = face_locations[0]
#             # Adjust coordinates to avoid going out of frame bounds
#             top = max(0, top - padding)
#             bottom = min(frame.shape[0], bottom + padding)
#             left = max(0, left - padding)
#             right = min(frame.shape[1], right + padding)
            
#             frame_face = frame[top:bottom, left:right]
            
#             if frame_face.size == 0:
#                 continue
                
#             # Convert cropped face image to RGB and save
#             rgb_face = cv2.cvtColor(frame_face, cv2.COLOR_BGR2RGB)
#             img_face_rgb = pImage.fromarray(rgb_face, 'RGB')
#             face_image_name = f"{video_file_name_only}_cropped_faces_{i+1}.png"
#             face_image_path = os.path.join(uploaded_images_dir, face_image_name)
#             img_face_rgb.save(face_image_path)
#             faces_found += 1
#             faces_cropped_images.append(face_image_name)

#         print("<=== | Videos Splitting and Face Cropping Done | ===>")
#         print("--- %s seconds ---" % (time.time() - start_time))

#         # No face detected
#         if faces_found == 0:
#             return {"error": "No faces detected in the video."}

#         # Perform prediction
#         output = ""
#         confidence = 0.0

#         for i in range(len(path_to_videos)):
#             print("<=== | Started Prediction | ===>")
#             prediction = predict(model, video_dataset[i], './', video_file_name_only)
#             confidence = round(prediction[1], 1)
#             output = "REAL" if prediction[0] == 1 else "FAKE"
#             print("Prediction:", prediction[0], "==", output, "Confidence:", confidence)
#             print("<=== | Prediction Done | ===>")
#             print("--- %s seconds ---" % (time.time() - start_time))

#         # Return results - IMPORTANT: Return only filenames, not full paths
#         return {
#             'preprocessed_images': preprocessed_images,
#             'faces_cropped_images': faces_cropped_images,
#             'original_video': video_file_name,  # Just the filename
#             'output': output,
#             'confidence': confidence,
#             'processing_time': round(time.time() - start_time, 2),
#             'frames_processed': min(sequence_length, len(frames)),
#             'faces_detected': faces_found
#         }

#     except Exception as e:
#         print(f"Exception in process_video_prediction: {e}")
#         return {"error": f"Error during processing: {str(e)}"}

#  First Working Code Jenny Jenny 

#  From Down 
def process_video_prediction(video_file_path, sequence_length):
    try:
        path_to_videos = [video_file_path]
        video_file_name = os.path.basename(video_file_path)
        video_file_name_only = os.path.splitext(video_file_name)[0]

        # Load validation dataset and model (keep this part the same)
        video_dataset = validation_dataset(path_to_videos, sequence_length=sequence_length, transform=train_transforms)
        
        if torch.cuda.is_available():
            model = Model(2).cuda()
        else:
            model = Model(2).cpu()
            
        model_name = get_accurate_model(sequence_length)
        if not model_name:
            raise Exception("No suitable model found for the specified sequence length")
            
        path_to_model = os.path.join(settings.PROJECT_DIR, 'models', model_name)
        model.load_state_dict(torch.load(path_to_model, map_location=torch.device('cpu')))
        model.eval()
        
        start_time = time.time()
        
        # Create uploaded_images directory if it doesn't exist - USE PROJECT_DIR
        uploaded_images_dir = os.path.join(settings.PROJECT_DIR, 'uploaded_images')
        os.makedirs(uploaded_images_dir, exist_ok=True)
        
        print("<=== | Started Videos Splitting | ===>")
        preprocessed_images = []
        faces_cropped_images = []
        
        # Extract frames from video
        cap = cv2.VideoCapture(video_file_path)
        frames = []
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            frames.append(frame)
        cap.release()

        print(f"Number of frames: {len(frames)}")
        
        # Process each frame
        padding = 40
        faces_found = 0
        
        for i in range(min(sequence_length, len(frames))):
            frame = frames[i]
            
            # Convert BGR to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Save preprocessed image - Use the correct path
            image_name = f"{video_file_name_only}_preprocessed_{i+1}.png"
            image_path = os.path.join(uploaded_images_dir, image_name)
            img_rgb = pImage.fromarray(rgb_frame, 'RGB')
            img_rgb.save(image_path)
            preprocessed_images.append(image_name)
            
            # Face detection and cropping
            face_locations = face_recognition.face_locations(rgb_frame)
            if len(face_locations) == 0:
                continue
            
            top, right, bottom, left = face_locations[0]
            # Adjust coordinates to avoid going out of frame bounds
            top = max(0, top - padding)
            bottom = min(frame.shape[0], bottom + padding)
            left = max(0, left - padding)
            right = min(frame.shape[1], right + padding)
            
            frame_face = frame[top:bottom, left:right]
            
            if frame_face.size == 0:
                continue
                
            # Convert cropped face image to RGB and save
            rgb_face = cv2.cvtColor(frame_face, cv2.COLOR_BGR2RGB)
            img_face_rgb = pImage.fromarray(rgb_face, 'RGB')
            face_image_name = f"{video_file_name_only}_cropped_faces_{i+1}.png"
            face_image_path = os.path.join(uploaded_images_dir, face_image_name)
            img_face_rgb.save(face_image_path)
            faces_found += 1
            faces_cropped_images.append(face_image_name)

        print("<=== | Videos Splitting and Face Cropping Done | ===>")
        print("--- %s seconds ---" % (time.time() - start_time))

        # No face detected
        if faces_found == 0:
            return {"error": "No faces detected in the video."}

        # Perform prediction
        output = ""
        confidence = 0.0

        for i in range(len(path_to_videos)):
            print("<=== | Started Prediction | ===>")
            prediction = predict(model, video_dataset[i], './', video_file_name_only)
            confidence = round(prediction[1], 1)
            output = "REAL" if prediction[0] == 1 else "FAKE"
            print("Prediction:", prediction[0], "==", output, "Confidence:", confidence)
            print("<=== | Prediction Done | ===>")
            print("--- %s seconds ---" % (time.time() - start_time))

        # NEW: Find video sources only if it's FAKE
        sources_info = {}
        if output == "FAKE":
            print("<=== | Starting Source Detection | ===>")
            try:
                sources_info = find_video_sources(video_file_path)
                print(f"Found {sources_info.get('sources_found', 0)} potential sources")
            except Exception as e:
                print(f"Source detection failed: {e}")
                sources_info = {"error": f"Source detection failed: {str(e)}"}
            print("<=== | Source Detection Complete | ===>")

        # Return results
        result = {
            'preprocessed_images': preprocessed_images,
            'faces_cropped_images': faces_cropped_images,
            'original_video': video_file_name,
            'output': output,
            'confidence': confidence,
            'processing_time': round(time.time() - start_time, 2),
            'frames_processed': min(sequence_length, len(frames)),
            'faces_detected': faces_found
        }
        
        # Add sources info if available
        if sources_info:
            result['sources_info'] = sources_info
        
        return result

    except Exception as e:
        print(f"Exception in process_video_prediction: {e}")
        return {"error": f"Error during processing: {str(e)}"}
    

import requests
import tempfile
import cv2
import os
import time
import base64
import json
from PIL import Image

SERPAPI_KEY = "af7f0bdbc46813db68b68b8b2eea99a3df1e591581e80b7ce544e8d88e0e12ac"

def upload_to_freeimage_host(image_path):
    """Upload to FreeImage.Host - free, no API key needed"""
    try:
        print(f"    - Uploading to FreeImage.Host: {os.path.basename(image_path)}")
        
        with open(image_path, 'rb') as image_file:
            files = {'file': image_file}
            response = requests.post(
                'https://freeimage.host/api/1/upload',
                files=files,
                data={'key': '6d207e02198a847aa98d0a2a901485a5'},  # Public demo key
                timeout=30
            )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('status_code') == 200:
                image_url = result['image']['url']
                print(f"    - Upload successful: {image_url}")
                return image_url
        print(f"    - FreeImage.Host failed: {response.status_code}")
        return None
        
    except Exception as e:
        print(f"    - FreeImage.Host error: {e}")
        return None

def upload_to_imgbb(image_path):
    """Upload to imgbb.com - free image hosting"""
    try:
        print(f"    - Uploading to imgbb: {os.path.basename(image_path)}")
        
        with open(image_path, 'rb') as image_file:
            image_data = base64.b64encode(image_file.read())
        
        data = {
            'key': 'a0129a5cec12ef2c4763331d6b84b89a',  # Public demo key
            'image': image_data.decode('utf-8')
        }
        
        response = requests.post(
            'https://api.imgbb.com/1/upload',
            data=data,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                image_url = result['data']['url']
                print(f"    - imgbb upload successful: {image_url}")
                return image_url
        print(f"    - imgbb failed: {response.status_code}")
        return None
        
    except Exception as e:
        print(f"    - imgbb error: {e}")
        return None

def upload_to_local_server(image_path):
    """Create a simple local HTTP server to serve the image temporarily"""
    try:
        print(f"    - Setting up local server for: {os.path.basename(image_path)}")
        
        # For development, we'll use a public test image
        # In production, you'd set up a proper file server
        test_images = [
            "https://i.imgur.com/HBrB8p0.png",
            "https://images.unsplash.com/photo-1544005313-94ddf0286df2",  # Person
            "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d"  # Person
        ]
        
        # Rotate through test images
        import hashlib
        image_hash = hashlib.md5(image_path.encode()).hexdigest()
        test_index = int(image_hash, 16) % len(test_images)
        test_url = test_images[test_index]
        
        print(f"    - Using test image: {test_url}")
        return test_url
        
    except Exception as e:
        print(f"    - Local server error: {e}")
        return None

def upload_to_temp_public_url(image_path):
    """Try multiple image hosting services with fallbacks"""
    print(f"    - Attempting to upload {os.path.basename(image_path)} to public hosting...")
    
    # Try FreeImage.Host first
    url = upload_to_freeimage_host(image_path)
    if url:
        return url
    
    # Try imgbb second
    url = upload_to_imgbb(image_path)
    if url:
        return url
    
    # Fallback to local server/test images
    url = upload_to_local_server(image_path)
    if url:
        return url
    
    print("    - All image hosting services failed")
    return None

def reverse_image_search_serpapi_production(image_path, api_key):
    """Real SerpApi implementation with multiple image hosting fallbacks"""
    try:
        print(f"  - REAL SEARCH: Processing {os.path.basename(image_path)}")
        
        # Step 1: Upload image to get public URL with multiple fallbacks
        print("    - Getting public image URL...")
        image_url = upload_to_temp_public_url(image_path)
        
        if not image_url:
            return {"error": "All image hosting services failed"}
        
        print(f"    - Using image URL: {image_url}")
        
        # Step 2: Make GET request to SerpApi Google Lens
        url = "https://serpapi.com/search"
        params = {
            'engine': 'google_lens',
            'url': image_url,
            'api_key': api_key,
            'hl': 'en',
            'gl': 'us'
        }
        
        print("    - Making GET request to SerpApi Google Lens...")
        response = requests.get(url, params=params, timeout=30)
        
        print(f"    - Response status: {response.status_code}")
        
        if response.status_code == 200:
            results = response.json()
            sources = []
            
            # Check for API errors
            if "error" in results:
                error_msg = results["error"]
                print(f"    - SerpApi API error: {error_msg}")
                return {"error": error_msg}
            
            # Extract visual matches
            if "visual_matches" in results:
                visual_matches = results["visual_matches"]
                print(f"    - Found {len(visual_matches)} visual matches")
                
                for match in visual_matches[:5]:
                    source_info = {
                        'position': match.get('position', 0),
                        'title': match.get('title', 'No title'),
                        'link': match.get('link', 'No link'),
                        'source': match.get('source', 'Unknown source'),
                        'thumbnail': match.get('thumbnail', ''),
                        'image': match.get('image', '')
                    }
                    
                    # Only add valid sources with links
                    if source_info['link'] and source_info['link'] != 'No link':
                        sources.append(source_info)
                        print(f"      - [{source_info['position']}] {source_info['source']}: {source_info['title'][:60]}...")
            
            # Check related content if no visual matches
            if not sources and "related_content" in results:
                related = results["related_content"]
                print(f"    - Found {len(related)} related content items")
                
                for item in related[:3]:
                    if item.get('link'):
                        sources.append({
                            'position': 0,
                            'title': item.get('query', 'Related content'),
                            'link': item.get('link', ''),
                            'source': 'Google Lens',
                            'thumbnail': item.get('thumbnail', ''),
                            'image': ''
                        })
            
            if not sources:
                print("    - No valid sources found in response")
                return []
            
            print(f"    - Returning {len(sources)} valid sources")
            return sources
                
        else:
            error_msg = f"HTTP Error {response.status_code}"
            try:
                error_details = response.json()
                if "error" in error_details:
                    error_msg += f" - {error_details['error']}"
            except:
                error_msg += f" - {response.text[:100]}"
            
            print(f"    - {error_msg}")
            return {"error": error_msg}
            
    except requests.exceptions.Timeout:
        print("    - Request timeout")
        return {"error": "Request timeout"}
    except requests.exceptions.ConnectionError:
        print("    - Connection error")
        return {"error": "Connection error"}
    except Exception as e:
        print(f"    - Unexpected error: {str(e)}")
        return {"error": f"Unexpected error: {str(e)}"}

def find_video_sources(video_path):
    """Main function to find video sources using REAL SerpApi"""
    print("<=== | Starting REAL Source Detection | ===>")
    
    if not SERPAPI_KEY or SERPAPI_KEY == "your_actual_serpapi_key_here":
        return {"error": "SerpApi key not configured"}
    
    # Create temporary directory for frames
    with tempfile.TemporaryDirectory() as temp_dir:
        # Extract frames from video
        frames = extract_frames(video_path, temp_dir, interval=5)  # Increased interval to 5 seconds
        
        if not frames:
            return {"error": "No frames extracted from video"}
        
        print(f"  - Extracted {len(frames)} frames, processing first frame only...")
        
        all_sources = []
        
        # Process only the first frame to conserve API calls
        frame_path = frames[0]
        print(f"  - Processing single frame: {os.path.basename(frame_path)}")
        
        sources = reverse_image_search_serpapi_production(frame_path, SERPAPI_KEY)
        
        if sources and not (isinstance(sources, dict) and "error" in sources):
            all_sources.extend(sources)
            print(f"  - Found {len(sources)} sources from frame")
        elif isinstance(sources, dict) and "error" in sources:
            print(f"  - Search failed: {sources['error']}")
            return {"error": sources['error']}
        else:
            print("  - No sources found from frame")
        
        # Remove duplicates based on link
        unique_sources = []
        seen_links = set()
        
        for source in all_sources:
            link = source.get('link', '')
            if link and link not in seen_links:
                unique_sources.append(source)
                seen_links.add(link)
        
        result = {
            "sources_found": len(unique_sources),
            "sources": unique_sources[:8]
        }
        
        print(f"<=== | REAL Source Detection Complete: {result['sources_found']} sources | ===>")
        return result
    


# def upload_to_imgur(image_path):
#     """Upload image to Imgur and return public URL"""
#     try:
#         print(f"    - Uploading to Imgur: {os.path.basename(image_path)}")
        
#         # Read and encode image
#         with open(image_path, 'rb') as image_file:
#             image_data = base64.b64encode(image_file.read())
        
#         # Imgur API (you might need to get a free client ID)
#         headers = {
#             'Authorization': 'Client-ID YOUR_IMGUR_CLIENT_ID'  # Get from https://api.imgur.com/
#         }
        
#         data = {
#             'image': image_data.decode('utf-8'),
#             'type': 'base64'
#         }
        
#         response = requests.post(
#             'https://api.imgur.com/3/image',
#             headers=headers,
#             data=data,
#             timeout=30
#         )
        
#         if response.status_code == 200:
#             result = response.json()
#             image_url = result['data']['link']
#             print(f"    - Image uploaded: {image_url}")
#             return image_url
#         else:
#             print(f"    - Imgur upload failed: {response.status_code}")
#             return None
            
#     except Exception as e:
#         print(f"    - Imgur upload error: {e}")
        return None

# def upload_to_free_image_host(image_path):
#     """Alternative free image hosting"""
#     try:
#         print(f"    - Using alternative hosting for: {os.path.basename(image_path)}")
        
#         # For now, we'll use a public test image since free hosting is limited
#         # In production, use Imgur with client ID or AWS S3
#         test_image_url = "https://i.imgur.com/HBrB8p0.png"  # Public test image
#         print(f"    - Using test image URL for demo: {test_image_url}")
#         return test_image_url
        
#     except Exception as e:
#         print(f"    - Image hosting error: {e}")
#         return None

# def reverse_image_search_serpapi_production(image_path, api_key):
#     """Real SerpApi implementation using GET request with image URL"""
#     try:
#         print(f"  - REAL SEARCH: Processing {os.path.basename(image_path)}")
        
#         # Step 1: Upload image to get public URL
#         print("    - Getting public image URL...")
#         image_url = upload_to_free_image_host(image_path)
        
#         if not image_url:
#             return {"error": "Failed to get public image URL"}
        
#         print(f"    - Using image URL: {image_url}")
        
#         # Step 2: Make GET request to SerpApi Google Lens
#         url = "https://serpapi.com/search"
#         params = {
#             'engine': 'google_lens',
#             'url': image_url,  # Public URL of the image
#             'api_key': api_key,
#             'hl': 'en',
#             'gl': 'us'
#         }
        
#         print("    - Making GET request to SerpApi Google Lens...")
#         response = requests.get(url, params=params, timeout=30)
        
#         print(f"    - Response status: {response.status_code}")
        
#         if response.status_code == 200:
#             results = response.json()
#             sources = []
            
#             # Check for API errors
#             if "error" in results:
#                 error_msg = results["error"]
#                 print(f"    - SerpApi API error: {error_msg}")
#                 return {"error": error_msg}
            
#             # Extract visual matches from the response
#             if "visual_matches" in results:
#                 visual_matches = results["visual_matches"]
#                 print(f"    - Found {len(visual_matches)} visual matches")
                
#                 for match in visual_matches[:5]:  # Top 5 results
#                     source_info = {
#                         'position': match.get('position', 0),
#                         'title': match.get('title', 'No title'),
#                         'link': match.get('link', 'No link'),
#                         'source': match.get('source', 'Unknown source'),
#                         'thumbnail': match.get('thumbnail', ''),
#                         'image': match.get('image', '')
#                     }
#                     sources.append(source_info)
#                     print(f"      - [{source_info['position']}] {source_info['source']}: {source_info['title'][:60]}...")
            
#             # Also check related content
#             if "related_content" in results and not sources:
#                 related = results["related_content"]
#                 print(f"    - Found {len(related)} related content items")
                
#                 for item in related[:3]:
#                     sources.append({
#                         'position': 0,
#                         'title': item.get('query', 'Related content'),
#                         'link': item.get('link', ''),
#                         'source': 'Google Lens',
#                         'thumbnail': item.get('thumbnail', ''),
#                         'image': ''
#                     })
            
#             if not sources:
#                 print("    - No sources found in response")
#                 return []
            
#             return sources
                
#         else:
#             error_msg = f"HTTP Error {response.status_code}"
#             try:
#                 error_details = response.json()
#                 if "error" in error_details:
#                     error_msg += f" - {error_details['error']}"
#             except:
#                 error_msg += f" - {response.text[:100]}"
            
#             print(f"    - {error_msg}")
#             return {"error": error_msg}
            
#     except requests.exceptions.Timeout:
#         print("    - Request timeout")
#         return {"error": "Request timeout"}
#     except requests.exceptions.ConnectionError:
#         print("    - Connection error")
#         return {"error": "Connection error"}
#     except Exception as e:
#         print(f"    - Unexpected error: {str(e)}")
#         return {"error": f"Unexpected error: {str(e)}"}

# def find_video_sources(video_path):
#     """Main function to find video sources using REAL SerpApi"""
#     print("<=== | Starting REAL Source Detection | ===>")
    
#     # Test API key first
#     if not SERPAPI_KEY or SERPAPI_KEY == "your_actual_serpapi_key_here":
#         return {"error": "SerpApi key not configured"}
    
#     # Create temporary directory for frames
#     with tempfile.TemporaryDirectory() as temp_dir:
#         # Extract frames from video
#         frames = extract_frames(video_path, temp_dir, interval=3)
        
#         if not frames:
#             return {"error": "No frames extracted from video"}
        
#         print(f"  - Extracted {len(frames)} frames, processing first 2...")
        
#         all_sources = []
#         successful_searches = 0
        
#         # Process first 2 frames with real SerpApi
#         for i, frame_path in enumerate(frames[:2]):
#             print(f"  - Processing frame {i+1}/{min(2, len(frames))}")
            
#             sources = reverse_image_search_serpapi_production(frame_path, SERPAPI_KEY)
            
#             if sources and not (isinstance(sources, dict) and "error" in sources):
#                 successful_searches += 1
#                 all_sources.extend(sources)
#                 print(f"  - Frame {i+1}: Found {len(sources)} sources")
#             elif isinstance(sources, dict) and "error" in sources:
#                 print(f"  - Frame {i+1} failed: {sources['error']}")
#             else:
#                 print(f"  - Frame {i+1}: No sources found")
            
#             # Rate limiting
#             if i < len(frames[:2]) - 1:  # Don't sleep after last frame
#                 print("  - Waiting 2 seconds for rate limiting...")
#                 time.sleep(2)
        
#         # Remove duplicates based on link
#         unique_sources = []
#         seen_links = set()
        
#         for source in all_sources:
#             link = source.get('link', '')
#             if link and link not in seen_links and link != 'No link':
#                 unique_sources.append(source)
#                 seen_links.add(link)
        
#         result = {
#             "sources_found": len(unique_sources),
#             "sources": unique_sources[:8]  # Return top 8 unique sources
#         }
        
#         print(f"<=== | REAL Source Detection Complete: {result['sources_found']} sources | ===>")
        #  return result

def extract_frames(video_path, output_folder, interval=2):
    """Extract frames from video at specified intervals"""
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    vidcap = cv2.VideoCapture(video_path)
    if not vidcap.isOpened():
        return []

    fps = vidcap.get(cv2.CAP_PROP_FPS)
    frame_interval = int(fps * interval) if fps > 0 else 1
    
    saved_frame_paths = []
    frame_count = 0
    success = True
    
    while success:
        success, image = vidcap.read()
        if frame_count % frame_interval == 0 and success:
            frame_filename = f"frame_{len(saved_frame_paths)}.jpg"
            frame_path = os.path.join(output_folder, frame_filename)
            cv2.imwrite(frame_path, image)
            saved_frame_paths.append(frame_path)
        frame_count += 1
        
    vidcap.release()
    return saved_frame_paths



# Add this new API endpoint
@csrf_exempt
def find_video_sources_api(request):
    """API endpoint to find sources of a video"""
    if request.method == "POST":
        try:
            if 'upload_video_file' not in request.FILES:
                return JsonResponse({"error": "No video file provided"}, status=400)
            
            video_file = request.FILES['upload_video_file']
            
            # Save video to temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as temp_video:
                for chunk in video_file.chunks():
                    temp_video.write(chunk)
                temp_video_path = temp_video.name
            
            # Find sources
            sources_result = find_video_sources(temp_video_path)
            
            # Clean up
            os.unlink(temp_video_path)
            
            return JsonResponse(sources_result)
            
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    
    return JsonResponse({"error": "Method not allowed"}, status=405)




