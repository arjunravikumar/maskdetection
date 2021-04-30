import cv2
import sys
import numpy as np
import youtube_dl
import boto3
import math
import time
import datetime
from pytz import timezone

startTime = 0
endTime = 0
timeDiff = 0
momentum = 0
previousSavedTime = 0
checkAndSaveMasks = True
avgTimeWhenEveyoneWearsMasks = 1.5
avgTimeWhenEveryoneDoesntWearsMasks = 2.5

s3BucketNameForFullImage = "wegmansmaskdetection"
s3BucketNameForIndividualImages = "wegmansmaskdetection"

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
        color = (0, 255, 255)
    thickness = 1
    img = cv2.rectangle(img,start_point, end_point,color,thickness)
    textLocation = (math.ceil(left), int(top))
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
    global s3BucketNameForFullImage,s3BucketNameForFullImage,index
    s3Bucket = boto3.client('s3', region_name='us-east-1')
    s3Bucket.upload_file("peopleWithBoundingBoxes"+index+".jpg", s3BucketNameForFullImage, "peopleWithBoundingBoxes.jpg")

def saveImagesOfPeopleWithoutMasks(peopleArray,percentOfPeopleWithoutMasks):
    global previousSavedTime,s3BucketNameForIndividualImages
    s3Bucket = boto3.client('s3', region_name='us-east-1')
    currTime = time.time()
    imagesOfPeopleNotWearingMask = []
    previousSavedTime = round(startTime)
    for i in range(len(peopleArray)):
        fName = peopleArray[i]
        location = "peoplewithoutmask/"+str(round(currTime))+"/person"+str(i)+".jpg"
        imagesOfPeopleNotWearingMask.append(location)
        s3Bucket.upload_file(fName, s3BucketNameForIndividualImages, location)
    if(len(imagesOfPeopleNotWearingMask) > 0):
        respo = putNotWornMaskPeopleInDB(round(currTime),round(percentOfPeopleWithoutMasks),imagesOfPeopleNotWearingMask,s3BucketNameForIndividualImages)

def createDDBtable():
    dynamodb = boto3.client('dynamodb', region_name='us-east-1')
    tableName = 'NotWornMask'
    existingTables = dynamodb.list_tables()['TableNames']
    if tableName not in existingTables:
        table = dynamodb.create_table(
            TableName=tableName,
            KeySchema=[
                {
                    'AttributeName': 'time',
                    'KeyType': 'HASH'  # Partition key
                }
            ],
            AttributeDefinitions=[
                {
                    'AttributeName': 'time',
                    'AttributeType': 'N'
                }
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 10,
                'WriteCapacityUnits': 10
            }
        )
    else:
        print("Table "+tableName+" already exists")

def putNotWornMaskPeopleInDB(time, percentOfPeopleWithoutMasks, imagesPaths, s3BucketName, dynamodb=None):
    if not dynamodb:
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    table = dynamodb.Table('NotWornMask')
    response = table.put_item(
       Item={
            'time': time,
            's3BucketName' : s3BucketName,
            'percentOfPeopleWithoutMasks': percentOfPeopleWithoutMasks,
            'imagesPaths': imagesPaths
        }
    )
    return response

def changeBackgroundColour(img,safe,precentageOfPeopleNotWearingMask):
    h,w=img.shape[0:2]
    base_size=h+30,w+30,3
    base=np.zeros(base_size,dtype=np.uint8)
    if(safe):
        color = (0,255,0)
    else:
        color = (0,0,255)
    cv2.rectangle(base,(0,0),(w+30,h+30),color,30)
    base[15:h+15,15:w+15]=img
    textLocation = (15, h+25)
    base = cv2.putText(base, "People Not Wearing Mask: "+ str(round(precentageOfPeopleNotWearingMask,2))+"%", \
                       textLocation, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,0), 1, cv2.LINE_AA)
    estTime = datetime.datetime.now(timezone('EST'))
    edtTime = estTime + datetime.timedelta(hours = 1)
    dt_string = edtTime.strftime("%d/%m/%Y %H:%M:%S")
    timeLocation = (15, 15)
    base = cv2.putText(base, str(dt_string), \
                       timeLocation, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,0), 1, cv2.LINE_AA)
    return base

def captureImage(checkAndSaveMasks):
    global index
    video_url = 'https://www.youtube.com/watch?v=oIBERbq2tLA'
    ydl_opts = {}
    ydl = youtube_dl.YoutubeDL(ydl_opts)
    try:
        ydl.cache.remove()
        info_dict = ydl.extract_info(video_url, download=False)
    except youtube_dl.DownloadError as error:
        pass
    formats = info_dict.get('formats',None)
    peopleWithoutMasks = []
    numberOfPeopleWithNoMask = 0
    for f in formats:
        if(f["height"] == 720):
            url = f['url']
            cap = cv2.VideoCapture(url)
            ret, videoFrame = cap.read()
            frame = videoFrame.copy()
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
                                if(maskStatus == "False"):
                                    numberOfPeopleWithNoMask +=1
                                if(checkAndSaveMasks and maskStatus == "False"):
                                    left = math.ceil(w * person["BoundingBox"]['Left'])
                                    top = math.ceil(h * person["BoundingBox"]['Top'])
                                    height = math.ceil(h*person["BoundingBox"]['Height'])
                                    width = math.ceil(w*person["BoundingBox"]['Width'])
                                    crop_img = videoFrame[top:top+height, left:left+width]
                                    cv2.imwrite("person"+str(i)+".jpg", crop_img)
                                    peopleWithoutMasks.append("person"+str(i)+".jpg")
                                if(faceBoxDetails!= None):
                                    frame = showBoundingBoxPositionForFace(h,w,faceBoxDetails,frame,maskStatus)
                        frame = showBoundingBoxPositionsForEachPerson(h,w,person["BoundingBox"],frame,maskStatus,faceCoverConfidence)
            cap.release()
    precentageOfPeopleNotWearingMask = 0
    if(len(peopleWithoutMasks) > 0):
        saveImagesOfPeopleWithoutMasks(peopleWithoutMasks,len(peopleWithoutMasks)/len(response['Persons'])*100)
    if(len(response['Persons'])>0):
        precentageOfPeopleNotWearingMask = (numberOfPeopleWithNoMask/len(response['Persons']))*100
    safe = True
    if(numberOfPeopleWithNoMask > 0):
        safe = False
    frame = changeBackgroundColour(frame,safe,precentageOfPeopleNotWearingMask)
    cv2.imwrite("peopleWithBoundingBoxes"+index+".jpg", frame)
    putImageInBucket()
    peopleWithoutMasks = []
    cv2.destroyAllWindows()
    return (numberOfPeopleWithNoMask == 0)

if __name__ == '__main__':
    index = ""
    if(len(sys.argv)>1):
        index = sys.argv[1]
    createDDBtable()
    while(True):
        startTime = time.time()
        if(round(startTime)-previousSavedTime>10):
            checkAndSaveMasks = True
        else:
            checkAndSaveMasks = False
        safetyStatus = captureImage(checkAndSaveMasks)
        endTime = time.time()
        timeDiff = endTime-startTime
        timeDiff = round(timeDiff,2)
        print(safetyStatus)
        if(safetyStatus):
            avgTimeWhenEveyoneWearsMasks += timeDiff
            avgTimeWhenEveyoneWearsMasks = round(avgTimeWhenEveyoneWearsMasks/2,2)
        else:
            avgTimeWhenEveryoneDoesntWearsMasks += timeDiff
            avgTimeWhenEveryoneDoesntWearsMasks = round(avgTimeWhenEveryoneDoesntWearsMasks/2,2)
        print(timeDiff,momentum)
        hyperParam = 0.2
        momentum = (hyperParam * momentum) + ((1 - hyperParam) * round(timeDiff,1))
        momentum = round(momentum,2) + (avgTimeWhenEveryoneDoesntWearsMasks-avgTimeWhenEveyoneWearsMasks)
        momentum = max(momentum,1.5)
        time.sleep(momentum)
