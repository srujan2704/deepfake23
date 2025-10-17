#!/usr/bin/env bash
set -o errexit

echo "Creating models directory..."
mkdir -p models

echo "Downloading 10-frame model from Google Drive..."
# Download the model file (replace FILE_ID with your actual file ID)
FILE_ID="1UX8jXUXyEjhLLZ38tcgOwGsZ6XFSLDJ-"  # ← REPLACE THIS WITH YOUR ACTUAL FILE ID
wget --no-check-certificate "https://docs.google.com/uc?export=download&id=$FILE_ID" -O models/model_84_acc_10_frames_final_data.pt

echo "Installing light dependencies first..."
pip install Django==5.0.6 gunicorn==21.2.0 whitenoise==6.6.0 
pip install django-cors-headers==4.3.1 asgiref==3.8.1 sqlparse==0.5.0
pip install numpy==1.24.3 Pillow==10.0.1 matplotlib==3.7.1 requests==2.31.0
pip install opencv-python==4.8.1.78

echo "Installing lighter PyTorch CPU version..."
pip install torch==1.13.1+cpu torchvision==0.14.1+cpu --index-url https://download.pytorch.org/whl/cpu

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Build completed successfully!"