import boto3
import datetime
import json
from urllib2 import Request
from collections import Counter
from pytz import timezone
import pytz

def startRDS(rds,rdslist):
    for i in rdslist:
        print i
        rds.start_db_instance(DBInstanceIdentifier=i)

def stopRDS(rds,rdslist):
    for i in rdslist:
        print i
        rds.stop_db_instance(DBInstanceIdentifier=i)

def main():

    print ("Running RDS Scheduler")
    accountid = boto3.client('sts').get_caller_identity().get('Account')

    ec2 = boto3.client('ec2')
    awsRegions = ec2.describe_regions()['Regions']

    daysActive = 'default'
    for region in awsRegions:
        try:
            awsregion = region['RegionName']

            defaulttz_now = datetime.datetime.now(pytz.timezone('EST'))
            now = defaulttz_now.strftime("%H%M")
            nowMax = defaulttz_now - datetime.timedelta(minutes=59)
            nowMax = nowMax.strftime("%H%M")
            nowDay = defaulttz_now.strftime("%a").lower()

            # Declare Lists
            startList = []
            stopList = []

            print ("Creating", region['RegionName'], "instance lists...")
            customTagLen = len('scheduler:rds-startstop')
            rds = boto3.client('rds',region_name=awsregion)
            rdsinstances = rds.describe_db_instances()
            for i in rdsinstances['DBInstances']:
                print "I"
                print i
                rdsname = i['DBInstanceIdentifier']
                print rdsname
                arn = "arn:aws:rds:%s:%s:db:%s"%(awsregion,accountid,rdsname)
                rdstags = rds.list_tags_for_resource(ResourceName=arn)
                if 'TagList' in rdstags:
                    for t in rdstags['TagList']:
                        if t['Key'][:customTagLen] == 'scheduler:rds-startstop':
                            print "has scheduler tag"

                            ptag = t['Value'].split(":")

                            # Split out Tag & Set Variables to default
                            default1 = 'default'
                            default2 = 'true'
                            state = i['DBInstanceStatus']
                            print state

                            # Parse tag-value
                            if len(ptag) >= 1:
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

                            # Append to stop list
                            if stopTime >= str(nowMax) and stopTime <= str(now) and \
                                    isActiveDay == True and state == "available":
                                stopList.append(rdsname)
                                print (rdsname, " added to STOP list")

            # Execute Start and Stop Commands
            if startList:
                print ("Starting", len(startList), "instances", startList)
                startRDS(rds,startList)
            else:
                print ("No Instances to Start")

            if stopList:
                print ("Stopping", len(stopList) ,"instances", stopList)
                stopRDS(rds,stopList)
            else:
                print ("No Instances to Stop")


        except Exception as e:
            print ("Exception: "+str(e))
            continue

if __name__ == '__main__':
   main()
