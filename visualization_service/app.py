from flask import Flask, render_template, Response, redirect, request, jsonify
from flask_cors import CORS
import redis
import json
from multiprocessing import Process
import numpy as np
import cv2
import random
import time
from utils.redis import serialize_img
from utils.redis import get_last
from utils.visualization import *
from config.loader import FLASK_HOSTNAME, FLASK_PORT
from config.loader import cfg, CAMERAS, NUM_THREADS, REDIS_HOSTNAME, REDIS_PORT, STREAM_MAXLEN, \
    demo_height, demo_width


app = Flask(__name__, template_folder='./templates')
CORS(app)


#----------------------- Initialize global variables: -----------------------
global camera_ids
camera_ids = [camera_info['id'] for camera_info in CAMERAS]

global last_ids, recent_processed_time, last_fps
last_ids = {}
recent_processed_time = {}
last_fps = {}
for camera_id in camera_ids:
    last_ids[camera_id] = 0
    recent_processed_time[camera_id] = []
    last_fps[camera_id] = 0


# Init Redis
global conn
conn = redis.Redis(host=REDIS_HOSTNAME, port=REDIS_PORT)
if not conn.ping():
    raise Exception("Redis unavailable")
print("Connect Redis successfully")
#----------------------- END OF Initialize global variables. -----------------------

#----------------------- Functions: -----------------------
def visualization(frame, frame_info, business_results, camera_id):
    # business_results = {
    #     "ids_mapping_weapon_brought": ids_mapping_weapon_brought,
    #     "exist_weapon_brought": exist_weapon_brought,
    #     "warning": warning,
    #     "current_people": current_people,
    #     "current_weapons": current_weapons
    # }

    global recent_processed_time, last_fps

    warning = business_results["warning"]
    ids_mapping_weapon_brought = business_results["ids_mapping_weapon_brought"]
    current_people = business_results["current_people"]
    current_weapons = business_results["current_weapons"]

    if warning:
        put_text(frame, (200,200,400,200), "WARNING!!!", font_scale = 1, font_thickness = 2, label_color=(0,0,255))

    plot_person_tracking(frame=frame, current_people=current_people)
    plot_machete_warning(frame, ids_mapping_weapon_brought, current_people, current_weapons)

    # Display the FPS and the annotated frame:
    elapsed_time = time.time() - frame_info["timestamp"]
    recent_processed_time[camera_id].append(elapsed_time)
    if len(recent_processed_time[camera_id]) == 10:
        last_fps[camera_id] = len(recent_processed_time[camera_id]) / sum(recent_processed_time[camera_id])
        # recent_processed_time[camera_id].remove(recent_processed_time[camera_id][0])
        recent_processed_time[camera_id] = []
    mean_fps = last_fps[camera_id]
    frame_width, frame_height = frame.shape[1], frame.shape[0]
    cv2.putText(frame, f"FPS: {mean_fps:.2f}", (int(frame_width*0.7), int(frame_height*0.1)), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

    frame = cv2.resize(frame, (demo_width, demo_height))

    return frame

def generate_frames(camera_id):
    global conn
    global last_ids

    topic = f'business_camera:{camera_id}'

    while True:
        last_ids[camera_id], frame, json_data = get_last(conn, topic, last_id=last_ids[camera_id])
        if frame is None:
            continue

        frame_info, business_results = json_data["frame_info"], json_data["business_results"]

        frame = visualization(frame, frame_info, business_results, camera_id)

        ret, jpeg = cv2.imencode('.jpg', frame)
        if not ret:
            continue
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
        
#----------------------- END OF Functions. -----------------------

@app.route('/')
def index():
    return render_template("index.html", camera_ids = camera_ids)

@app.errorhandler(404)
def page_not_found(error):
    return render_template('404.html'), 404

@app.route('/video/<camera_id>')
def video(camera_id):
    return Response(generate_frames(camera_id), mimetype='multipart/x-mixed-replace; boundary=frame')


if __name__ == '__main__':
    app.run(host = FLASK_HOSTNAME, port = FLASK_PORT, debug = True)