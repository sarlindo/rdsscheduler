######################################################################################################################
#  Copyright 2016 Amazon.com, Inc. or its affiliates. All Rights Reserved.                                           #
#                                                                                                                    #
#  Licensed under the Amazon Software License (the "License"). You may not use this file except in compliance        #
#  with the License. A copy of the License is located at                                                             #
#                                                                                                                    #
#      http://aws.amazon.com/asl/                                                                                    #
#                                                                                                                    #
#  or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES #
#  OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions    #
#  and limitations under the License.                                                                                #
######################################################################################################################
# Change Log
# --------------------------------------------------------------------------------------------------------------------
# Author:       Arlindo Santos
# Description:  Add a check to see if instances have tags because this lambda fuction would not work and would fail
#               if an instance did not have any tags "if hasattr(i,'tags') and i.tags is not None:"
# Date:         Dec/06/2016
# ---------------------------------------------------------------------------------------------------------------------
# --------------------------------------------------------------------------------------------------------------------
# Author:       Arlindo Santos
# Description:  Add abilty to send message which includes instance tags such as Environment and Name to SNS topic and
#               add new field for topic ARN in dynamodb table
# Date:         Oct/12/2017
# ---------------------------------------------------------------------------------------------------------------------
# --------------------------------------------------------------------------------------------------------------------
# Author:       Arlindo Santos
# Description:  Add pytz timezone aware lib to handle proper local timezones because of overlapping
#               issues with UTC.
# Date:         Dec/12/2017
# ---------------------------------------------------------------------------------------------------------------------

import boto3
import datetime
import json
from urllib2 import Request
from collections import Counter
from pytz import timezone
import pytz

def send_sns(topicArn,message):
    sns = boto3.client('sns')

    response = sns.publish(
        TopicArn=topicArn,
        Message=message
    )

def putCloudWatchMetric(region, instance_id, instance_state):

    cw = boto3.client('cloudwatch')

    cw.put_metric_data(
        Namespace='RDSScheduler',
        MetricData=[{
            'MetricName': instance_id,
            'Value': instance_state,

            'Unit': 'Count',
            'Dimensions': [
                {
                    'Name': 'Region',
                    'Value': region
                }
            ]
        }]

    )
def startRDS(rds,rdslist):
    for i in rdslist:
        rds.start_db_instance(DBInstanceIdentifier=i)

def stopRDS(rds,rdslist):
    for i in rdslist:
        rds.stop_db_instance(DBInstanceIdentifier=i)

def lambda_handler(event, context):

    print ("Running RDS Scheduler")
    accountid = boto3.client('sts').get_caller_identity().get('Account')

    ec2 = boto3.client('ec2')
    cf = boto3.client('cloudformation')
    outputs = {}
    stack_name = context.invoked_function_arn.split(':')[6].rsplit('-', 2)[0]
    response = cf.describe_stacks(StackName=stack_name)
    for e in response['Stacks'][0]['Outputs']:
        outputs[e['OutputKey']] = e['OutputValue']
    ddbTableName = outputs['DDBTableName']

    awsRegions = ec2.describe_regions()['Regions']
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(ddbTableName)
    response = table.get_item(
        Key={
            'SolutionName': 'RDSScheduler'
        }
    )
    item = response['Item']

    # Reading Default Values from DynamoDB
    customTagName = str(item['CustomTagName'])
    customTagLen = len(customTagName)
    defaultStartTime = str(item['DefaultStartTime'])
    defaultStopTime = str(item['DefaultStopTime'])
    defaultTimeZone = str(item['DefaultTimeZone'])
    defaultDaysActive = str(item['DefaultDaysActive'])
    sendData = str(item['SendAnonymousData']).lower()
    createMetrics = str(item['CloudWatchMetrics']).lower()
    UUID = str(item['UUID'])
    SNSTopicArn = str(item['SNSTopic'])

    for region in awsRegions:
        try:
            awsregion = region['RegionName']

            defaulttz_now = datetime.datetime.now(pytz.timezone(defaultTimeZone))
            now = defaulttz_now.strftime("%H%M")
            nowMax = defaulttz_now - datetime.timedelta(minutes=59)
            nowMax = nowMax.strftime("%H%M")
            nowDay = defaulttz_now.strftime("%a").lower()

            # Declare Lists
            startList = []
            stopList = []

            print ("Creating", region['RegionName'], "instance lists...")

            rds = boto3.client('rds',region_name=awsregion)
            rdsinstances = rds.describe_db_instances()
            for i in rdsinstances['DBInstances']:
                rdsname = i['DBInstanceIdentifier']
                arn = "arn:aws:rds:%s:%s:db:%s"%(awsregion,accountid,rdsname)
                rdstags = rds.list_tags_for_resource(ResourceName=arn)
                if 'TagList' in rdstags:
                    for t in rdstags['TagList']:
                        if t['Key'][:customTagLen] == customTagName:

                            ptag = t['Value'].split(";")

                            # Split out Tag & Set Variables to default
                            default1 = 'default'
                            default2 = 'true'
                            startTime = defaultStartTime
                            stopTime = defaultStopTime
                            timeZone = defaultTimeZone
                            daysActive = defaultDaysActive
                            state = i['DBInstanceStatus']

                            # Post current state of the instances
                            if createMetrics == 'enabled':
                                if state == "available":
                                    putCloudWatchMetric(awsregion, rdsname, 1)
                                if state == "stopped":
                                    putCloudWatchMetric(awsregion, rdsname, 0)

                            # Parse tag-value
                            if len(ptag) >= 1:
                                if ptag[0].lower() in (default1, default2):
                                    startTime = defaultStartTime
                                else:
                                    startTime = ptag[0]
                                    stopTime = ptag[0]
                            if len(ptag) >= 2:
                                stopTime = ptag[1]
                            if len(ptag) >= 3:
                                timeZone = ptag[2].upper()
                                ttz_now = datetime.datetime.now(pytz.timezone(timeZone))
                                now = ttz_now.strftime("%H%M")
                                nowMax = ttz_now - datetime.timedelta(minutes=59)
                                nowMax = nowMax.strftime("%H%M")
                                nowDay = ttz_now.strftime("%a").lower()
                            if len(ptag) >= 4:
                                daysActive = ptag[3].lower()

                            isActiveDay = False

                            # Days Interpreter
                            if daysActive == "all":
                                isActiveDay = True
                            elif daysActive == "weekdays":
                                weekdays = ['mon', 'tue', 'wed', 'thu', 'fri']
                                if (nowDay in weekdays):
                                    isActiveDay = True
                            else:
                                daysActive = daysActive.split(",")
                                for d in daysActive:
                                    if d.lower() == nowDay:
                                        isActiveDay = True

                            # Append to start list
                            if startTime >= str(nowMax) and startTime <= str(now) and \
                                    isActiveDay == True and state == "stopped":
                                startList.append(rdsname)
                                print (rdsname, " added to START list")
                                if createMetrics == 'enabled':
                                    putCloudWatchMetric(awsregion, rdsname, 1)

                            # Append to stop list
                            if stopTime >= str(nowMax) and stopTime <= str(now) and \
                                    isActiveDay == True and state == "available":
                                stopList.append(rdsname)
                                print (rdsname, " added to STOP list")
                                if createMetrics == 'enabled':
                                    putCloudWatchMetric(awsregion, rdsname, 0)

            # Execute Start and Stop Commands
            if startList:
                print ("Starting", len(startList), "instances", startList)
                #send_sns(SNSTopicArn,"Starting " + str(len(startList)) + " instances " + ','.join(startList))
                startRDS(rds,startList)
            else:
                print ("No Instances to Start")

            if stopList:
                print ("Stopping", len(stopList) ,"instances", stopList)
                #send_sns(SNSTopicArn,"Stopping " + str(len(stopList)) + " instances " + ','.join(stopList))
                stopRDS(rds,stopList)
            else:
                print ("No Instances to Stop")


        except Exception as e:
            print ("Exception: "+str(e))
            continue
