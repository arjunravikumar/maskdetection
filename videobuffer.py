import cv2
import numpy as np
import youtube_dl
import boto3
import math
import time

def showBoundingBoxPositionsForEachPerson(imageHeight, imageWidth, box, img, maskStatus, confidence): 
    left = imageWidth * box['Left']
    top = imageHeight * box['Top']
    start_point = (int(left), int(top))
    end_point = (math.ceil(left + (imageWidth*box['Width'])), math.ceil(top + (imageHeight*box['Height'])))
    if(maskStatus == "True"):
        color = (0, 255 , 0)
    elif(maskStatus == "False"):
        color = (0, 0 , 255)
    else:
        color = (255, 0, 0)
    thickness = 2
    img = cv2.rectangle(img,start_point, end_point,color,thickness)
    textLocation = (math.ceil(left + (imageWidth*box['Width'])), int(top))
    if(int(confidence)>1):
        img = cv2.putText(img, "Confidence :"+ str(round(confidence,1))+"%", textLocation, cv2.FONT_HERSHEY_SIMPLEX, 0.3, color, 1, cv2.LINE_AA)
    return img

def showBoundingBoxPositionForFace(imageHeight, imageWidth, box, img ,maskStatus):
    left = imageWidth * box['Left']
    top = imageHeight * box['Top']
    start_point = (int(left), int(top))
    end_point = (math.ceil(left + (imageWidth*box['Width'])), math.ceil(top + (imageHeight*box['Height'])))
    if(maskStatus == "True"):
        color = (0, 255 , 0)
    else:
        color = (0, 0 , 255)
    print(maskStatus,color)
    thickness = 1
    img = cv2.rectangle(img,start_point, end_point,color,thickness)
    return img

def extractFaceDetails(bodyPart):
    confidence = 0.0
    maskStatus = "False"
    box = None
    if( "EquipmentDetections" in bodyPart):
        for equipement in bodyPart["EquipmentDetections"]:
            box = equipement["BoundingBox"]
            if( "CoversBodyPart" in equipement and "Confidence" in equipement["CoversBodyPart"]):
                confidence = equipement["CoversBodyPart"]["Confidence"]
                maskStatus = str(equipement["CoversBodyPart"]["Value"])
    return box,confidence,maskStatus

def putImageInBucket():
    s3Bucket = boto3.client('s3', region_name='us-east-1')
    s3Bucket.upload_file("peopleWithBoundingBoxed.jpg", "wegmansmaskdetection", "peopleWithBoundingBoxes.jpg")

def peopleWithoutMasks(peopleArray):
    s3Bucket = boto3.client('s3', region_name='us-east-1')
    saveTime = time.time()
    for i in range(len(peopleArray)):
        fName = peopleArray[i]
        s3Bucket.upload_file(fName, "wegmansmaskdetection", "/peoplewithoutmask/"+saveTime+"/"+i+".jpg")
    
def captureImage(checkAndSaveMasks):
    video_url = 'https://www.youtube.com/watch?v=oIBERbq2tLA'
    ydl_opts = {}
    ydl = youtube_dl.YoutubeDL(ydl_opts)
    try:
        ydl.cache.remove()
        info_dict = ydl.extract_info(video_url, download=False)
    except youtube_dl.DownloadError as error:
        pass
    formats = info_dict.get('formats',None)
    for f in formats:
        if(f["height"] == 720):
            url = f['url']
            cap = cv2.VideoCapture(url)
            ret, videoFrame = cap.read()
            frame = videoFrame.copy()
            peopleWithoutMasks = []
            if ret:
                hasFrame, imageBytes = cv2.imencode(".jpg", frame)
                if hasFrame:
                    session = boto3.session.Session()
                    rekognition = session.client('rekognition', region_name='us-east-1')
                    response = rekognition. detect_protective_equipment(
                            Image={
                                'Bytes': imageBytes.tobytes(),
                            }
                        )
                    for i in range(len(response['Persons'])):
                        person = response['Persons'][i]
                        h, w, c = frame.shape
                        maskStatus="Not Sure"
                        faceCoverConfidence = 0.0
                        for i in range(len(person["BodyParts"])):
                            bodyPart = person["BodyParts"][i]
                            if("Name" in bodyPart and bodyPart["Name"] == "FACE"):
                                faceBoxDetails,faceCoverConfidence,maskStatus = extractFaceDetails(bodyPart)
                                print("maskworn? "+ maskStatus,faceBoxDetails)
                                if(checkAndSaveMasks and maskStatus == "False"):
                                    left = imageWidth * person["BoundingBox"]['Left']
                                    top = imageHeight * person["BoundingBox"]['Top']
                                    height = h*person["BoundingBox"]['Height']
                                    width = w*person["BoundingBox"]['Width']
                                    if(maskStatus == "True"):
                                    crop_img = img[left:left+height, top:top+width]
                                    cv2.imwrite("person"+str(i)+".jpg", frame)
                                    peopleWithoutMasks.append("person"+str(i)+".jpg")
                                if(faceBoxDetails!= None):
                                    frame = showBoundingBoxPositionForFace(h,w,faceBoxDetails,frame,maskStatus)
                        frame = showBoundingBoxPositionsForEachPerson(h,w,person["BoundingBox"],frame,maskStatus,faceCoverConfidence)
                    cv2.imwrite("peopleWithBoundingBoxed.jpg", frame)
            cap.release()
    putImageInBucket()
    saveImagesOfPeopleWithoutMasks(peopleWithoutMasks)
    cv2.destroyAllWindows()

if __name__ == '__main__':
    previousSavedTime = 0
    checkAndSaveMasks = True
    while(True):
        seconds = time.time()
        if(previousSavedTime-seconds>10):
            seconds = previousSavedTime
            checkAndSaveMasks = True
        captureImage(checkAndSaveMasks)
        time.sleep(1)
        checkAndSaveMasks = False
