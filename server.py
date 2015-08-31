MONGO_HOST = "localhost"
MONGO_PORT = 27017
#MONGO_HOST = os.environ['VEHICLE_DATA_PORT_27017_TCP_ADDR']
#MONGO_PORT = int(os.environ['VEHICLE_DATA_PORT_27017_TCP_PORT'])

CAFFE_ROOT = "/home/ubuntu/caffe/"
import sys
sys.path.insert (0, CAFFE_ROOT + "python")

IMAGE_ROOT = "/tmp/"
MODELS_ROOT = "/home/ubuntu/caffe/models/cars/"
from flask import Flask, request, Response, jsonify
from mongokit import Connection, Document
from StringIO import StringIO
import caffe, numpy as np
import urllib, datetime, requests, traceback


app = Flask (__name__)
app.config.from_object (__name__)
connection = Connection (app.config['MONGO_HOST'], app.config['MONGO_PORT'])

caffe.set_mode_cpu()
#blob = caffe.proto.caffe_pb2.BlobProto()
#data = open (MODELS_ROOT + "hdd_mean.binaryproto").read()
#blob.ParseFromString(data)
#mean_rs = np.array( caffe.io.blobproto_to_array(blob) )[0].mean(1).mean(1)
hdd_labels_file = MODELS_ROOT + "labels_450.txt"
labels = None

try:
    labels = np.loadtxt (hdd_labels_file, str, delimiter="\t")
except:
    app.logger.debug("[classifier] fuck, cant load label file")

c0 = caffe.Classifier (
            MODELS_ROOT + "deploy_450.prototxt",
            MODELS_ROOT + "450_45k.caffemodel",
            channel_swap = (2,1,0),
            raw_scale = 255,
            image_dims = (256, 256)
)
classifiers = [c0]

@connection.register
class Classification (Document):
    __collection__ = "classifications"
    __database__   = "cars_450"
    use_dot_notation = True
    skip_validation = True
    structure = {
        "image_url": unicode,
        "date_created": datetime.datetime,
        "top_1": {
                "class_name": unicode,
                "prob": float
        },
        "top_3": [
            {
                "class_name": unicode,
                "prob": float
            }
        ]
    }
    required_fields = [
        "image_url",
        "date_created",
        "top_1",
        "top_3"
    ]
@app.route("/classify")
def classify():
    try:
        num_outs = 5
        image_url = request.args.get ("image_url")
        image_file_name = IMAGE_ROOT + image_url.split("/")[-1]
        urllib.urlretrieve (image_url, image_file_name)
        app.logger.debug ("[classifier] image loaded to " + image_file_name)
        image = caffe.io.load_image(image_file_name)
        resized_image = caffe.io.resize_image (image, (256,256,3))
        res = np.zeros (num_outs * len (classifiers)).reshape (num_outs, len(classifiers))
        for i, x in enumerate (classifiers):
            res[:,i] = x.predict ([resized_image])[0]
        avg_probs = np.average (res, axis=1)
        top_k_idx = avg_probs.argsort()[-1:-4:-1]
        class_res = connection.Classification()
        class_res['image_url'] = image_url
        class_res['date_created'] = datetime.datetime.now()
        class_res['top_3'] = []
        for x in top_k_idx.tolist():
            res_dict = {}
            res_dict["class_name"] = labels.tolist()[x][0]
            res_dict["prob"] = avg_probs.tolist()[x]
            app.logger.debug (str(res_dict) + " " + image_file_name)
            class_res['top_3'].append (res_dict)
        class_res['top_1'] = class_res['top_3'][0]
        class_res.save()
        app.logger.debug ("[classifier] classification result saved." + str(class_res.to_json()))
        response = Response (response = class_res.to_json(), status=200, mimetype="application/json")
        return response
    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        app.logger.error (" ".join(traceback.format_tb (exc_traceback)))
        resp = jsonify ({"msg": "Server Error"})
        resp.status_code = 500
        return resp


if __name__ == "__main__":
    if not app.debug:
        import logging
        from logging.handlers import RotatingFileHandler
        handler = RotatingFileHandler ("classifier_server.log", maxBytes=1024 * 20, backupCount=20)
        handler.setFormatter (logging.Formatter (
            '%(asctime)s %(levelname)s: %(message)s '
            '[in %(pathname)s:%(lineno)d]'
        ))
        handler.setLevel (logging.WARNING)
        app.logger.addHandler (handler)
    app.run(host="0.0.0.0")

