# import cv2
# import os
# import requests
# from django.conf import settings
# import time

# class ReverseImageSearch:
#     def __init__(self):
#         self.SERPAPI_KEY = settings.SERPAPI_KEY
#         self.config = settings.REVERSE_SEARCH_CONFIG
    
#     def extract_frames(self, video_path, interval):
#         """Extract frames from video at specified intervals"""
#         if not os.path.exists(self.config['OUTPUT_FOLDER']):
#             os.makedirs(self.config['OUTPUT_FOLDER'])
        
#         try:
#             vidcap = cv2.VideoCapture(video_path)
#             if not vidcap.isOpened():
#                 print(f"Could not open video: {video_path}")
#                 return []
            
#             fps = vidcap.get(cv2.CAP_PROP_FPS)
#             frame_interval = int(fps * interval) if fps > 0 else 1
            
#             saved_frame_paths = []
#             frame_count = 0
#             success = True
            
#             while success and len(saved_frame_paths) < self.config['MAX_FRAMES_TO_ANALYZE']:
#                 success, image = vidcap.read()
#                 if frame_count % frame_interval == 0 and success:
#                     frame_filename = f"frame_{len(saved_frame_paths)}.jpg"
#                     frame_path = os.path.join(self.config['OUTPUT_FOLDER'], frame_filename)
#                     cv2.imwrite(frame_path, image)
#                     saved_frame_paths.append(frame_path)
#                     print(f"Extracted frame: {frame_path}")
#                 frame_count += 1
            
#             vidcap.release()
#             return saved_frame_paths
            
#         except Exception as e:
#             print(f"Frame extraction error: {e}")
#             return []
    
#     def reverse_search_frame(self, image_path):
#         """Perform reverse image search on a single frame"""
#         try:
#             # Mock implementation for localhost testing
#             # Replace with actual SerpApi call when ready
            
#             print(f"Performing reverse search for: {image_path}")
            
#             # Simulate API delay
#             time.sleep(1)
            
#             # Mock response data
#             mock_sources = [
#                 {
#                     "title": "Social Media Post - Local Test",
#                     "link": "https://facebook.com/post/123",
#                     "source": "Facebook",
#                     "thumbnail": ""
#                 },
#                 {
#                     "title": "Video Platform - Local Test", 
#                     "link": "https://youtube.com/watch/abc",
#                     "source": "YouTube",
#                     "thumbnail": ""
#                 }
#             ]
            
#             return mock_sources
            
#         except Exception as e:
#             print(f"Reverse search error: {e}")
#             return []
    
#     def analyze_video_spread(self, video_path):
#         """Main function to analyze video spread across web"""
#         print(f"Analyzing video spread for: {video_path}")
        
#         # Extract frames
#         frames = self.extract_frames(video_path, self.config['FRAME_INTERVAL_SECONDS'])
        
#         if not frames:
#             return {
#                 "sources": [],
#                 "totalMatches": 0,
#                 "framesAnalyzed": 0,
#                 "searchDate": time.strftime('%Y-%m-%d %H:%M:%S'),
#                 "note": "No frames extracted from video"
#             }
        
#         # Perform reverse search on frames
#         all_sources = []
#         for frame_path in frames:
#             sources = self.reverse_search_frame(frame_path)
#             all_sources.extend(sources)
        
#         # Remove duplicates and format results
#         unique_sources = []
#         seen_links = set()
        
#         for source in all_sources:
#             if source['link'] not in seen_links:
#                 seen_links.add(source['link'])
#                 unique_sources.append({
#                     'title': source['title'],
#                     'url': source['link'],
#                     'platform': source.get('source', 'Unknown'),
#                     'confidence': min(80 + len(unique_sources) * 5, 95),
#                     'thumbnail': source.get('thumbnail', '')
#                 })
        
#         return {
#             'sources': unique_sources,
#             'totalMatches': len(unique_sources),
#             'framesAnalyzed': len(frames),
#             'searchDate': time.strftime('%Y-%m-%d %H:%M:%S')
#         }