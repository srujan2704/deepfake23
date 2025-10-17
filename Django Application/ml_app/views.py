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
import requests
import tempfile
import base64

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

# ========== API ENDPOINTS ==========

@csrf_exempt
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
        result = process_video_prediction(video_file_path, sequence_length)
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

# ========== IMPROVED VIDEO PROCESSING AND SOURCE DETECTION ==========

def process_video_prediction(video_file_path, sequence_length):
    try:
        path_to_videos = [video_file_path]
        video_file_name = os.path.basename(video_file_path)
        video_file_name_only = os.path.splitext(video_file_name)[0]

        # Load validation dataset and model
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
        
        # Create uploaded_images directory if it doesn't exist
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
            
            # Save preprocessed image
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
                sources_info = find_video_sources_improved(video_file_path)
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

# ========== IMPROVED SOURCE DETECTION FUNCTIONS ==========

# SerpApi configuration
SERPAPI_KEY = "af7f0bdbc46813db68b68b8b2eea99a3df1e591581e80b7ce544e8d88e0e12ac"

def get_direct_media_url(image_path):
    """Serve the actual frame through Django's media system"""
    try:
        # Get the relative path from MEDIA_ROOT
        media_root = settings.MEDIA_ROOT
        if image_path.startswith(media_root):
            relative_path = os.path.relpath(image_path, media_root)
            media_url = f"{settings.MEDIA_URL}{relative_path}"
            
            # For external APIs, we need the full URL
            if settings.DEBUG:
                # Development - use localhost
                full_url = f"http://localhost:8000{media_url}"
            else:
                # Production - use your domain
                from django.contrib.sites.models import Site
                current_site = Site.objects.get_current()
                full_url = f"http://{current_site.domain}{media_url}"
            
            print(f"    - Using direct media URL: {full_url}")
            return full_url
        else:
            print(f"    - Image not in MEDIA_ROOT: {image_path}")
            return None
            
    except Exception as e:
        print(f"    - Error getting direct media URL: {str(e)}")
        return None
    
def save_frame_to_media(image_path, video_file_name_only):
    """Save frame to media directory for public access"""
    try:
        print(f"    - Saving frame to media directory: {os.path.basename(image_path)}")
        
        # Create frames directory in media
        frames_dir = os.path.join(settings.MEDIA_ROOT, 'source_frames')
        os.makedirs(frames_dir, exist_ok=True)
        
        # Create unique filename
        import uuid
        unique_id = uuid.uuid4().hex[:8]
        frame_filename = f"{video_file_name_only}_frame_{unique_id}.jpg"
        frame_dest_path = os.path.join(frames_dir, frame_filename)
        
        # Copy and optimize the frame
        img = pImage.open(image_path)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Resize if too large
        max_size = 800
        if img.size[0] > max_size or img.size[1] > max_size:
            img.thumbnail((max_size, max_size), pImage.Resampling.LANCZOS)
        
        # Save optimized version
        img.save(frame_dest_path, "JPEG", quality=85, optimize=True)
        
        # Return the media URL
        media_url = f"{settings.MEDIA_URL}source_frames/{frame_filename}"
        
        # For external APIs, need full URL
        if settings.DEBUG:
            full_url = f"http://localhost:8000{media_url}"
        else:
            from django.contrib.sites.models import Site
            current_site = Site.objects.get_current()
            full_url = f"http://{current_site.domain}{media_url}"
        
        print(f"    - Frame accessible at: {full_url}")
        return full_url
        
    except Exception as e:
        print(f"    - Error saving frame to media: {str(e)}")
        return None

def upload_to_temp_public_url(image_path):
    """MAIN FIX: Use the actual frame instead of test images"""
    print(f"    - Processing actual frame: {os.path.basename(image_path)}")
    
    # Extract video name for unique filenames
    video_file_name_only = "source_frame"
    if 'uploaded_file_' in image_path:
        # Extract the uploaded file name from path
        import re
        match = re.search(r'uploaded_file_(\d+)', image_path)
        if match:
            video_file_name_only = f"uploaded_file_{match.group(1)}"
    
    # STRATEGY 1: Save to media directory and serve via Django
    media_url = save_frame_to_media(image_path, video_file_name_only)
    if media_url:
        return media_url
    
    # STRATEGY 2: Try direct media URL (if frame is already in media)
    direct_url = get_direct_media_url(image_path)
    if direct_url:
        return direct_url
    
    # STRATEGY 3: If all else fails, DON'T use Danny DeVito - skip the frame instead
    print("    - WARNING: Could not serve frame, skipping this frame")
    return None

def find_video_sources_improved(video_path):
    """Enhanced source detection with better fallback handling"""
    print("<=== | Starting ENHANCED Source Detection | ===>")
    
    if not SERPAPI_KEY or SERPAPI_KEY == "your_actual_serpapi_key_here":
        return {"error": "SerpApi key not configured"}
    
    start_time = time.time()
    
    # Create temporary directory for frames
    with tempfile.TemporaryDirectory() as temp_dir:
        # Extract multiple frames from different parts of the video
        frames = extract_multiple_frames_improved(video_path, temp_dir, num_frames=3)
        
        if not frames:
            return {"error": "No frames extracted from video"}
        
        print(f"  - Extracted {len(frames)} ACTUAL frames from video: {os.path.basename(video_path)}")
        
        all_sources = []
        successful_searches = 0
        
        # Process each ACTUAL frame
        for i, frame_path in enumerate(frames):
            print(f"  - Processing ACTUAL frame {i+1}/{len(frames)}: {os.path.basename(frame_path)}")
            
            # Use enhanced search with fallbacks
            sources = enhanced_reverse_image_search(frame_path, SERPAPI_KEY)
            
            if sources and not (isinstance(sources, dict) and "error" in sources):
                successful_searches += 1
                all_sources.extend(sources)
                print(f"    - Found {len(sources)} sources from ACTUAL frame")
            elif isinstance(sources, dict) and "error" in sources:
                print(f"    - Search failed: {sources['error']}")
            else:
                print(f"    - No sources found from ACTUAL frame")
            
            # Rate limiting between API calls
            if i < len(frames) - 1:
                time.sleep(2)
        
        # Process and filter sources
        filtered_sources = filter_and_rank_sources(all_sources)
        
        result = {
            "sources_found": len(filtered_sources),
            "sources": filtered_sources[:8],
            "frames_analyzed": successful_searches,
            "search_time": round(time.time() - start_time, 2),
            "note": "Using actual video frames with enhanced search"
        }
        
        if len(filtered_sources) == 0:
            result["sources"] = [{
                'position': 1,
                'title': 'No online sources detected for this video',
                'link': '',
                'source': 'Analysis System',
                'thumbnail': '',
                'image': '',
                'note': 'This video does not appear to be sourced from any publicly available online content'
            }]
            result["sources_found"] = 1
        
        print(f"<=== | Enhanced Source Detection Complete: {result['sources_found']} sources | ===>")
        return result

# def find_video_sources_improved(video_path):
#     """Improved source detection using multiple frames and better filtering"""
#     print("<=== | Starting IMPROVED Source Detection | ===>")
    
#     if not SERPAPI_KEY or SERPAPI_KEY == "your_actual_serpapi_key_here":
#         return {"error": "SerpApi key not configured"}
    
#     start_time = time.time()
    
#     # Create temporary directory for frames
#     with tempfile.TemporaryDirectory() as temp_dir:
#         # Extract multiple frames from different parts of the video
#         frames = extract_multiple_frames_improved(video_path, temp_dir, num_frames=5)
        
#         if not frames:
#             return {"error": "No frames extracted from video"}
        
#         print(f"  - Extracted {len(frames)} frames for analysis")
        
#         all_sources = []
#         successful_searches = 0
        
#         # Process each frame
#         for i, frame_path in enumerate(frames):
#             print(f"  - Processing frame {i+1}/{len(frames)}: {os.path.basename(frame_path)}")
            
#             sources = reverse_image_search_improved(frame_path, SERPAPI_KEY)
            
#             if sources and not (isinstance(sources, dict) and "error" in sources):
#                 successful_searches += 1
#                 all_sources.extend(sources)
#                 print(f"    - Found {len(sources)} sources from this frame")
#             elif isinstance(sources, dict) and "error" in sources:
#                 print(f"    - Search failed: {sources['error']}")
#             else:
#                 print(f"    - No sources found from this frame")
            
#             # Rate limiting between API calls
#             if i < len(frames) - 1:
#                 time.sleep(1)
        
#         # Process and filter sources
#         filtered_sources = filter_and_rank_sources(all_sources)
        
#         result = {
#             "sources_found": len(filtered_sources),
#             "sources": filtered_sources[:10],
#             "frames_analyzed": successful_searches,
#             "search_time": round(time.time() - start_time, 2)
#         }
        
#         print(f"<=== | Improved Source Detection Complete: {result['sources_found']} sources found | ===>")
#         return result

def extract_multiple_frames_improved(video_path, output_folder, num_frames=5):
    """Extract multiple frames from different timestamps in the video"""
    vidcap = cv2.VideoCapture(video_path)
    if not vidcap.isOpened():
        return []

    total_frames = int(vidcap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = vidcap.get(cv2.CAP_PROP_FPS)
    duration = total_frames / fps if fps > 0 else 0
    
    saved_frame_paths = []
    
    # Calculate frame positions for better coverage
    if duration > 0:
        intervals = [i * (duration / (num_frames + 1)) for i in range(1, num_frames + 1)]
    else:
        intervals = [int(i * (total_frames / (num_frames + 1))) for i in range(1, num_frames + 1)]
    
    for i, position in enumerate(intervals):
        try:
            if duration > 0:
                vidcap.set(cv2.CAP_PROP_POS_MSEC, position * 1000)
            else:
                vidcap.set(cv2.CAP_PROP_POS_FRAMES, position)
            
            success, image = vidcap.read()
            if success and image is not None:
                frame_filename = f"frame_{i}.jpg"
                frame_path = os.path.join(output_folder, frame_filename)
                
                # Resize image to optimize for API
                height, width = image.shape[:2]
                max_dim = 800
                if width > max_dim or height > max_dim:
                    scale = max_dim / max(width, height)
                    new_width = int(width * scale)
                    new_height = int(height * scale)
                    image = cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_AREA)
                
                cv2.imwrite(frame_path, image, [cv2.IMWRITE_JPEG_QUALITY, 85])
                saved_frame_paths.append(frame_path)
                
        except Exception as e:
            print(f"    - Error extracting frame {i}: {str(e)}")
            continue
    
    vidcap.release()
    return saved_frame_paths

def reverse_image_search_improved(image_path, api_key):
    """Improved reverse image search with better filtering for video sources"""
    try:
        print(f"    - Searching for video sources: {os.path.basename(image_path)}")
        
        # Get public image URL
        image_url = upload_to_temp_public_url(image_path)
        if not image_url:
            return {"error": "Failed to get public image URL"}
        
        print(f"    - Using image URL: {image_url}")
        
        # Make request to SerpApi Google Lens
        url = "https://serpapi.com/search"
        params = {
            'engine': 'google_lens',
            'url': image_url,
            'api_key': api_key,
            'hl': 'en',
            'gl': 'us'
        }
        
        response = requests.get(url, params=params, timeout=30)
        print(f"    - Response status: {response.status_code}")
        
        if response.status_code == 200:
            results = response.json()
            sources = []
            
            if "error" in results:
                error_msg = results["error"]
                print(f"    - SerpApi API error: {error_msg}")
                return {"error": error_msg}
            
            # Extract visual matches
            if "visual_matches" in results:
                visual_matches = results["visual_matches"]
                print(f"    - Found {len(visual_matches)} total matches")
                
                for match in visual_matches:
                    source_info = {
                        'position': match.get('position', 0),
                        'title': match.get('title', 'No title'),
                        'link': match.get('link', ''),
                        'source': match.get('source', 'Unknown source'),
                        'thumbnail': match.get('thumbnail', ''),
                        'image': match.get('image', ''),
                        'score': calculate_source_score(match)
                    }
                    
                    # Only add sources that are likely to contain videos
                    if is_video_related_source(source_info):
                        sources.append(source_info)
            
            print(f"    - Filtered to {len(sources)} video-related sources")
            return sources[:8]
                
        else:
            error_msg = f"HTTP Error {response.status_code}"
            print(f"    - {error_msg}")
            return {"error": error_msg}
            
    except Exception as e:
        print(f"    - Search error: {str(e)}")
        return {"error": f"Search error: {str(e)}"}

def calculate_source_score(source_info):
    """Calculate a relevance score for the source"""
    score = 0
    
    # Base score from position
    position = source_info.get('position', 100)
    if position <= 5:
        score += 30
    elif position <= 10:
        score += 20
    elif position <= 20:
        score += 10
    
    # Boost for video platforms
    video_platforms = ['youtube', 'vimeo', 'dailymotion', 'tiktok', 'instagram', 'facebook']
    source_lower = source_info.get('source', '').lower()
    title_lower = source_info.get('title', '').lower()
    
    for platform in video_platforms:
        if platform in source_lower or platform in title_lower:
            score += 25
            break
    
    # Boost for social media
    social_media = ['instagram', 'twitter', 'facebook', 'tiktok', 'reddit']
    for social in social_media:
        if social in source_lower:
            score += 20
            break
    
    # Boost for video keywords
    video_keywords = ['video', 'watch', 'youtube', 'tiktok', 'reel', 'short', 'clip', 'footage']
    for keyword in video_keywords:
        if keyword in title_lower:
            score += 15
            break
    
    return score

def is_video_related_source(source_info):
    """Check if the source is likely to contain video content"""
    title = source_info.get('title', '').lower()
    source = source_info.get('source', '').lower()
    link = source_info.get('link', '').lower()
    
    # Video platforms
    video_domains = [
        'youtube.com', 'youtu.be', 'vimeo.com', 'dailymotion.com',
        'tiktok.com', 'instagram.com', 'facebook.com', 'twitter.com',
        'reddit.com', 'twitch.tv', 'vimeo.com'
    ]
    
    # Check if link contains video platform domains
    for domain in video_domains:
        if domain in link:
            return True
    
    # Check for video-related keywords in title
    video_keywords = [
        'video', 'watch', 'youtube', 'tiktok', 'reel', 'short', 'clip',
        'footage', 'film', 'movie', 'recording', 'stream', 'live'
    ]
    
    for keyword in video_keywords:
        if keyword in title:
            return True
    
    # Social media platforms often contain videos
    social_platforms = ['instagram', 'tiktok', 'facebook', 'twitter', 'reddit']
    for platform in social_platforms:
        if platform in source:
            return True
    
    return False

def filter_and_rank_sources(all_sources):
    """Filter duplicates and rank sources by relevance"""
    seen_links = set()
    unique_sources = []
    
    for source in all_sources:
        link = source.get('link', '')
        if link and link not in seen_links:
            seen_links.add(link)
            unique_sources.append(source)
    
    # Sort by score (highest first), then by position
    unique_sources.sort(key=lambda x: (x.get('score', 0), -x.get('position', 100)), reverse=True)
    
    # Remove score from final output
    for source in unique_sources:
        if 'score' in source:
            del source['score']
    
    return unique_sources

# ========== IMAGE UPLOAD FUNCTIONS ==========

def upload_to_freeimage_host(image_path):
    """Upload to FreeImage.Host"""
    try:
        print(f"    - Uploading to FreeImage.Host: {os.path.basename(image_path)}")
        
        with open(image_path, 'rb') as image_file:
            files = {'file': image_file}
            response = requests.post(
                'https://freeimage.host/api/1/upload',
                files=files,
                data={'key': '6d207e02198a847aa98d0a2a901485a5'},
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
    """Upload to imgbb.com"""
    try:
        print(f"    - Uploading to imgbb: {os.path.basename(image_path)}")
        
        with open(image_path, 'rb') as image_file:
            image_data = base64.b64encode(image_file.read())
        
        data = {
            'key': 'a0129a5cec12ef2c4763331d6b84b89a',
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

# def upload_to_local_server(image_path):
#     """FIXED: Serve ACTUAL frames through Django media system"""
#     try:
#         print(f"    - SERIOUS FIX: Serving ACTUAL frame: {os.path.basename(image_path)}")
        
#         # Verify this is a real frame file
#         if not os.path.exists(image_path):
#             print(f"    - ERROR: Frame file doesn't exist: {image_path}")
#             return None
        
#         # Check file size to ensure it's a real image
#         file_size = os.path.getsize(image_path)
#         if file_size < 1000:  # Too small to be a real frame
#             print(f"    - WARNING: Frame file too small ({file_size} bytes)")
#             return None
        
#         # Extract video name for proper naming
#         video_file_name_only = "actual_frame"
#         if 'uploaded_file_' in image_path:
#             import re
#             match = re.search(r'uploaded_file_(\d+)', image_path)
#             if match:
#                 video_file_name_only = f"uploaded_file_{match.group(1)}"
        
#         # Use the existing save_frame_to_media function (which you already have)
#         actual_frame_url = save_frame_to_media(image_path, video_file_name_only)
        
#         if actual_frame_url:
#             print(f"    - SUCCESS: Actual frame served: {actual_frame_url}")
#             return actual_frame_url
#         else:
#             print(f"    - ERROR: Could not save frame to media")
#             return None
            
#     except Exception as e:
#         print(f"    - CRITICAL ERROR in local server: {str(e)}")
#         return None

# def upload_to_temp_public_url(image_path):
#     """Try multiple image hosting services with fallbacks"""
#     print(f"    - Attempting to upload {os.path.basename(image_path)} to public hosting...")
    
#     # Try FreeImage.Host first
#     url = upload_to_freeimage_host(image_path)
#     if url:
#         return url
    
#     # Try imgbb second
#     url = upload_to_imgbb(image_path)
#     if url:
#         return url
    
#     # Fallback to local server/test images
#     url = upload_to_local_server(image_path)
#     if url:
#         return url
    
#     print("    - All image hosting services failed")
#     return None

# ========== ADDITIONAL API ENDPOINT ==========

# def enhanced_reverse_image_search(image_path, api_key):
#     """Enhanced search with fallback strategies when Google Lens finds nothing"""
#     try:
#         print(f"    - Enhanced search for: {os.path.basename(image_path)}")
        
#         # Get public image URL
#         image_url = upload_to_temp_public_url(image_path)
#         if not image_url:
#             return {"error": "Failed to get public image URL"}
        
#         print(f"    - Using image URL: {image_url}")
        
#         # Strategy 1: Try Google Lens first
#         url = "https://serpapi.com/search"
#         params = {
#             'engine': 'google_lens',
#             'url': image_url,
#             'api_key': api_key,
#             'hl': 'en',
#             'gl': 'us'
#         }
        
#         response = requests.get(url, params=params, timeout=30)
#         print(f"    - Google Lens response: {response.status_code}")
        
#         if response.status_code == 200:
#             results = response.json()
            
#             if "error" in results:
#                 error_msg = results["error"]
#                 print(f"    - Google Lens error: {error_msg}")
                
#                 # If no results, try alternative approach
#                 if "hasn't returned any results" in error_msg:
#                     return try_alternative_search_strategies(image_url, api_key)
#                 return {"error": error_msg}
            
#             # Process normal results
#             if "visual_matches" in results:
#                 visual_matches = results["visual_matches"]
#                 print(f"    - Found {len(visual_matches)} matches")
                
#                 sources = []
#                 for match in visual_matches:
#                     source_info = {
#                         'position': match.get('position', 0),
#                         'title': match.get('title', 'No title'),
#                         'link': match.get('link', ''),
#                         'source': match.get('source', 'Unknown source'),
#                         'thumbnail': match.get('thumbnail', ''),
#                         'image': match.get('image', ''),
#                         'score': calculate_source_score(match)
#                     }
                    
#                     if is_video_related_source(source_info):
#                         sources.append(source_info)
                
#                 print(f"    - Filtered to {len(sources)} video sources")
#                 return sources[:8]
#             else:
#                 print("    - No visual matches in response")
#                 return try_alternative_search_strategies(image_url, api_key)
                
#         else:
#             print(f"    - HTTP Error: {response.status_code}")
#             return try_alternative_search_strategies(image_url, api_key)
            
#     except Exception as e:
#         print(f"    - Search error: {str(e)}")
#         return {"error": f"Search error: {str(e)}"}

def enhanced_reverse_image_search(image_path, api_key):
    """Enhanced search with direct file upload + URL fallback strategies"""
    try:
        print(f"    - Enhanced search for: {os.path.basename(image_path)}")
        
        # STRATEGY 1: Try direct file upload first (most reliable - no image hosting needed)
        print("    - Strategy 1: Trying direct file upload to SerpApi...")
        direct_sources = serpapi_direct_upload_search(image_path, api_key)
        
        if direct_sources and not (isinstance(direct_sources, dict) and "error" in direct_sources):
            print(f"    - ✅ Direct upload successful, found {len(direct_sources)} sources")
            return direct_sources[:8]
        
        # STRATEGY 2: Fallback to URL-based approach
        print("    - Strategy 2: Direct upload failed, trying URL-based approach...")
        
        # Get public image URL
        image_url = upload_to_temp_public_url(image_path)
        if not image_url:
            return {"error": "Failed to get public image URL"}
        
        print(f"    - Using image URL: {image_url}")
        
        # Make request to SerpApi Google Lens
        url = "https://serpapi.com/search"
        params = {
            'engine': 'google_lens',
            'url': image_url,
            'api_key': api_key,
            'hl': 'en',
            'gl': 'us'
        }
        
        response = requests.get(url, params=params, timeout=30)
        print(f"    - Google Lens response: {response.status_code}")
        
        if response.status_code == 200:
            results = response.json()
            
            if "error" in results:
                error_msg = results["error"]
                print(f"    - Google Lens error: {error_msg}")
                
                # If no results, try alternative approach
                if "hasn't returned any results" in error_msg:
                    return try_alternative_search_strategies(image_url, api_key)
                return {"error": error_msg}
            
            # Process normal results
            if "visual_matches" in results:
                visual_matches = results["visual_matches"]
                print(f"    - Found {len(visual_matches)} matches")
                
                sources = []
                for match in visual_matches:
                    source_info = {
                        'position': match.get('position', 0),
                        'title': match.get('title', 'No title'),
                        'link': match.get('link', ''),
                        'source': match.get('source', 'Unknown source'),
                        'thumbnail': match.get('thumbnail', ''),
                        'image': match.get('image', ''),
                        'score': calculate_source_score(match)
                    }
                    
                    if is_video_related_source(source_info):
                        sources.append(source_info)
                
                print(f"    - Filtered to {len(sources)} video sources")
                return sources[:8]
            else:
                print("    - No visual matches in response")
                return try_alternative_search_strategies(image_url, api_key)
                
        else:
            print(f"    - HTTP Error: {response.status_code}")
            return try_alternative_search_strategies(image_url, api_key)
            
    except Exception as e:
        print(f"    - Search error: {str(e)}")
        return {"error": f"Search error: {str(e)}"}
    
def try_alternative_search_strategies(image_url, api_key):
    """Try alternative search methods when Google Lens fails"""
    print("    - Trying alternative search strategies...")
    
    # Strategy 2: Try Google Images search instead of Lens
    try:
        url = "https://serpapi.com/search"
        params = {
            'engine': 'google_images',
            'q': f'"{image_url}"',  # Search by image URL
            'api_key': api_key,
            'hl': 'en',
            'gl': 'us'
        }
        
        response = requests.get(url, params=params, timeout=30)
        if response.status_code == 200:
            results = response.json()
            
            sources = []
            if "images_results" in results:
                for img_result in results["images_results"][:5]:  # Top 5 results
                    source_info = {
                        'position': len(sources) + 1,
                        'title': img_result.get('title', 'Image result'),
                        'link': img_result.get('link', ''),
                        'source': img_result.get('source', 'Google Images'),
                        'thumbnail': img_result.get('thumbnail', ''),
                        'image': img_result.get('original', ''),
                        'score': 10  # Lower score since it's not from Lens
                    }
                    
                    if is_video_related_source(source_info):
                        sources.append(source_info)
                
                if sources:
                    print(f"    - Found {len(sources)} sources via Google Images")
                    return sources
            
    except Exception as e:
        print(f"    - Alternative search error: {e}")
    
    # Strategy 3: Return informative message instead of empty results
    print("    - No matches found in any search engine")
    return [{
        'position': 1,
        'title': 'No online sources found for this video frame',
        'link': '',
        'source': 'System',
        'thumbnail': '',
        'image': '',
        'score': 0,
        'note': 'This video frame does not appear in any indexed online sources'
    }]

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
            
            # Find sources using improved detection
            sources_result = find_video_sources_improved(temp_video_path)
            
            # Clean up
            os.unlink(temp_video_path)
            
            return JsonResponse(sources_result)
            
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    
    return JsonResponse({"error": "Method not allowed"}, status=405)

# ========== USING GOOGLE SEARCH RESULTS LIBRARY APPROACH ==========


def serpapi_direct_upload_search(image_path, api_key):
    """Use direct file upload with SerpApi (like standalone script)"""
    try:
        print(f"    - Using SerpApi direct upload: {os.path.basename(image_path)}")
        
        # Verify file exists and is valid
        if not os.path.exists(image_path):
            print(f"    - ERROR: File doesn't exist: {image_path}")
            return {"error": "File not found"}
        
        # Check file size
        file_size = os.path.getsize(image_path)
        if file_size < 1000:
            print(f"    - WARNING: File too small ({file_size} bytes)")
            return {"error": "File too small"}
        
        # Use GoogleSearch library for direct upload
        from serpapi import GoogleSearch
        
        params = {
            "engine": "google_lens",
            "api_key": api_key,
            "upload_file": image_path  # Direct file upload - no image hosting needed!
        }

        search = GoogleSearch(params)
        results = search.get_dict()
        
        sources = []
        
        # Check for visual matches in the results
        if "visual_matches" in results:
            visual_matches = results["visual_matches"]
            print(f"    - Found {len(visual_matches)} potential matches via direct upload")
            
            for match in visual_matches[:10]:  # Top 10 matches
                source_info = {
                    'position': match.get('position', 0),
                    'title': match.get('title', 'No Title'),
                    'link': match.get('link', ''),
                    'source': match.get('source', 'Unknown source'),
                    'thumbnail': match.get('thumbnail', ''),
                    'image': match.get('image', ''),
                    'score': calculate_source_score(match)
                }
                
                if is_video_related_source(source_info):
                    sources.append(source_info)
                    print(f"      - [{source_info['position']}] {source_info['source']}: {source_info['title'][:60]}...")
        
        if sources:
            print(f"    - Returning {len(sources)} valid sources from direct upload")
            return sources
        else:
            print("    - No valid sources found via direct upload")
            return []
            
    except ImportError:
        print("    - ERROR: google_search_results library not installed. Run: pip install google-search-results")
        return {"error": "Required library not installed"}
    except Exception as e:
        print(f"    - SerpApi direct upload error: {e}")
        return {"error": f"SerpApi error: {str(e)}"}

def upload_to_local_server(image_path):
    """FIXED: Serve ACTUAL frames through Django media system - NO test images"""
    try:
        print(f"    - SERIOUS FIX: Serving ACTUAL frame: {os.path.basename(image_path)}")
        
        # Verify this is a real frame file
        if not os.path.exists(image_path):
            print(f"    - ERROR: Frame file doesn't exist: {image_path}")
            return None
        
        # Check file size to ensure it's a real image
        file_size = os.path.getsize(image_path)
        if file_size < 1000:  # Too small to be a real frame
            print(f"    - WARNING: Frame file too small ({file_size} bytes)")
            return None
        
        # Extract video name for proper naming
        video_file_name_only = "actual_frame"
        if 'uploaded_file_' in image_path:
            import re
            match = re.search(r'uploaded_file_(\d+)', image_path)
            if match:
                video_file_name_only = f"uploaded_file_{match.group(1)}"
        
        # Use the existing save_frame_to_media function
        actual_frame_url = save_frame_to_media(image_path, video_file_name_only)
        
        if actual_frame_url:
            print(f"    - SUCCESS: Actual frame served: {actual_frame_url}")
            return actual_frame_url
        else:
            print(f"    - ERROR: Could not save frame to media")
            return None
            
    except Exception as e:
        print(f"    - CRITICAL ERROR in local server: {str(e)}")
        return None

def upload_to_temp_public_url(image_path):
    """Use ACTUAL frames only - NO test images"""
    print(f"    - CRITICAL: Processing ACTUAL frame: {os.path.basename(image_path)}")
    
    # STRATEGY 1: Serve through Django media (MANDATORY)
    actual_url = upload_to_local_server(image_path)  # This now uses the FIXED version
    if actual_url:
        return actual_url
    
    # STRATEGY 2: If all else fails, SKIP the frame entirely
    print("    - CRITICAL: Could not serve actual frame - SKIPPING")
    return None