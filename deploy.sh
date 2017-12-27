S3BucketName="coderepo.arlindo.ca"
StackName="rds-scheduler"
DefaultStopTime="1900"

cd source
zip -r ../dist/rds-scheduler.zip *
aws s3 cp ../dist/rds-scheduler.zip s3://${S3BucketName}
cd ..

set +e
StackStatus=$(aws cloudformation describe-stacks --stack-name ${StackName} --query Stacks[0].StackStatus --output text)
set -e

if [ ${#StackStatus} -eq 0 ]
then
  aws cloudformation create-stack --stack-name ${StackName} \
      --template-body file://template/rds-scheduler.yaml \
    	--capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
    	--parameters \
        ParameterKey=DefaultStopTime,ParameterValue=${DefaultStopTime} \
    	  ParameterKey=S3BucketName,ParameterValue=${S3BucketName}
elif [ ${StackStatus} == 'CREATE_COMPLETE' -o ${StackStatus} == 'UPDATE_COMPLETE' ]
then
  echo "Update stack ${StackName} ..."
  ChangeSetName="${StackName}-$(uuidgen)"

  aws cloudformation create-change-set --stack-name ${StackName} \
      --template-body file://template/rds-scheduler.yaml \
      --change-set-name ${ChangeSetName} \
      --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
      --parameters \
        ParameterKey=DefaultStopTime,ParameterValue=${DefaultStopTime} \
        ParameterKey=S3BucketName,ParameterValue=${S3BucketName}
  sleep 30
  ChangeSetStatus=$(aws cloudformation describe-change-set  \
        --change-set-name ${ChangeSetName} \
        --stack-name ${StackName} \
        --query Status \
        --output text)
  if [ ${ChangeSetStatus} == 'FAILED' ]
	then
    echo "Update lambda code using zip file"
    FunctionName=$(aws lambda list-functions --query Functions[].FunctionName \
      | grep rdsSchedulerOptIn |sed s/\",*//g |tr -d '[:space:]')

      aws lambda update-function-code --function-name ${FunctionName} --zip-file fileb://dist/rds-scheduler.zip
  else
      echo "Execute change set ${ChangeSetName}"
      aws cloudformation execute-change-set --change-set-name ${ChangeSetName} --stack-name ${StackName}
  fi
fi
