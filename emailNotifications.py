import boto3
from dynamodb_json import json_util as json
from boto3.dynamodb.conditions import Attr
import time

sns = None

topicName = "WegmansMailNotification"
subscribers = []

def createTopic(topicName):
  global sns
  response = sns.create_topic(Name=topicName)
  topicArn = response["TopicArn"]
  return topicArn

def listAllTopics():
  global sns
  response = sns.list_topics()
  topics = response["Topics"]
  return topics

def createAnEmailSubscription(topicArn,emailID):
  global sns
  response = sns.subscribe(TopicArn=topicArn, Protocol="email", Endpoint=emailID)
  subscription_arn = response["SubscriptionArn"]
  return subscription_arn

def getAllSubscriptionsByTopic(topicArn):
  global sns
  response = sns.list_subscriptions_by_topic(TopicArn=topicArn)
  subscriptions = response["Subscriptions"]
  return subscriptions

def publishMessage(topicArn,subject,message):
  global sns
  response = sns.publish(TopicArn=topicArn,Message=message,Subject=subject)

def checkIfTopicAndSubscriptionExists():
  global sns,subscribers,topicName
  topicArn = ""
  sns = boto3.client("sns", region_name="us-east-1")
  topics = listAllTopics()
  for i in range(len(topics)):
    tArn = topics[i]["TopicArn"]
    topicNames = tArn.split(":")[5]
    if topicName == topicNames:
       topicArn = tArn
  if(topicArn == ""):
    topicArn = createTopic(topicName)
  subs = getAllSubscriptionsByTopic(topicArn)
  subscribersRequired = subscribers[:]
  for i in range(len(subs)):
    subEmail = subs[i]["Endpoint"]
    if subEmail in subscribersRequired:
      subscribersRequired.remove(subEmail)
  for i in range(len(subscribersRequired)):
    createAnEmailSubscription(topicArn,subscribersRequired[i])
  return topicArn

def fetchPeopleWithoutMaskDetails(fromTime):
  dynamodb = boto3.resource('dynamodb', region_name="us-east-1")
  table = dynamodb.Table('NotWornMask')
  response = table.scan(
    FilterExpression=Attr('time').gt(fromTime)
  )
  dynamodb_json = json.dumps(response['Items'])
  dynamodb_json = json.loads(dynamodb_json)
  return dynamodb_json


def publishAlertForUnsafeEnviornment(topicArn,msgString,noOfPeopleWithoutMasks):
  if(noOfPeopleWithoutMasks == 1):
    subject = str(noOfPeopleWithoutMasks) + "  person found without mask in the last 10 seconds"
  else:
    subject = str(noOfPeopleWithoutMasks) + "  people found without mask in the last 10 seconds"
  message = msgString
  publishMessage(topicArn,subject,message)

def processTheDynamoDBVal(ddbJson):
  strVal = "This is an automated mail.\n"
  numberOfPeopleNotWearingMask = 0
  for i in range(len(ddbJson)):
    timeSlotVal = ddbJson[i]
    if(timeSlotVal["percentOfPeopleWithoutMasks"] >= 50):
      strVal = strVal + "\n" + str(timeSlotVal["percentOfPeopleWithoutMasks"]) + "% of people were detected not wearing mask at around " + \
      str(round(time.time() - timeSlotVal["time"])) + " seconds ago. The images of the people not wearing masks can be obtained here "
      for j in range(len(timeSlotVal["imagesPaths"])):
        numberOfPeopleNotWearingMask+=1
        strVal = strVal + "\n\t https://"+timeSlotVal["s3BucketName"]+".s3.amazonaws.com/"+timeSlotVal["imagesPaths"][j]
  if(numberOfPeopleNotWearingMask > 0):
    strVal =  strVal + "\n\n\n There is a chance for the photos not to be accurate please verify the same before taking any action."
  return strVal,numberOfPeopleNotWearingMask
  
def checkForAlertingWhenPeopleAreNotWearingMasks(topicArn):
  lastSavedTime = time.time()-10
  while(True):
    print("fetchTime",lastSavedTime,"currTime",time.time())
    dynaDBVal = fetchPeopleWithoutMaskDetails(round(lastSavedTime))
    messageString, totalNumberOfPeople = processTheDynamoDBVal(dynaDBVal)
    if(totalNumberOfPeople > 0):
      publishAlertForUnsafeEnviornment(topicArn,messageString,totalNumberOfPeople)
    lastSavedTime = time.time()
    time.sleep(10)

def askUserForMailAdresses():
  global subscribers
  num = input("How many new subscriber email IDs are to be added? \n")
  num = int(num)
  for i in range(num):
    emailID = input("Enter email ID of subscriber " + str(i+1) +" : ")
    subscribers.append(emailID)

if __name__ == '__main__':
  askUserForMailAdresses()
  topicArn = checkIfTopicAndSubscriptionExists()
  checkForAlertingWhenPeopleAreNotWearingMasks(topicArn)
      
