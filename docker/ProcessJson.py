#!/usr/bin/env python
# Copyright 2016 Amazon.com, Inc. or its
# affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You may not
# use this file except in compliance with the License. A copy of the License is
# located at
#
#     http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is distributed on
# an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied. See the License for the specific language governing
# permissions and limitations under the License.
import os
import json
import urllib
from urllib.parse import unquote_plus
import boto3
import numpy as np
import pandas as pd


#Temp directory to store output file
csv_dir = '/csv'
#Parameters taken from the ECS Cluster
input_bucket_name = os.environ['s3InputBucket']
output_bucket_name = os.environ['s3OutputBucket']
sqsqueue_name = os.environ['SQSBatchQueue']
aws_region = os.environ['AWSRegion']
#Define s3 and SQS
s3 = boto3.client('s3', region_name=aws_region)
sqs = boto3.resource('sqs', region_name=aws_region)


#Create directories for storing temp output files
def create_dirs():
    for dirs in [csv_dir]:
        if not os.path.exists(dirs):
            os.makedirs(dirs)

#From the AWS repository.  This actually processes any file that is passed through, not just images
def process_images():
    """Process the image

    No real error handling in this sample code. In case of error we'll put
    the message back in the queue and make it visable again. It will end up in
    the dead letter queue after five failed attempts.

    """
    for message in get_messages_from_sqs():
        try:
            message_content = json.loads(message.body)
            image = unquote_plus(message_content
                                        ['Records'][0]['s3']['object']
                                        ['key'])
            s3.download_file(input_bucket_name, image, image)
            process_json(image)
            upload_image(image)
            cleanup_files(image)
        except:
            message.change_visibility(VisibilityTimeout=0)
            continue
        else:
            message.delete()


#Delete temp files when done
def cleanup_files(image):
    os.remove(image)
    os.remove(csv_dir + '/' + 'output.csv')

#Upload final output file to S3
def upload_image(image):
    s3.upload_file(csv_dir + '/' + 'output.csv',
                   output_bucket_name, 'csv/' + image + '.csv')


#Messages from SQS
def get_messages_from_sqs():
    results = []
    queue = sqs.get_queue_by_name(QueueName=sqsqueue_name)
    for message in queue.receive_messages(VisibilityTimeout=120,
                                          WaitTimeSeconds=20,
                                          MaxNumberOfMessages=10):
        results.append(message)
    return(results)


#This is the function that processes the JSON file
#NOTE: This function is set up to specifically handle patient-examples-general.json because it deals specifically with the "entry" dict
#Some additional work would need to be performed to ready this file for any json file that is thrown at it; namely better handling
#of mutli vs single-level dictionaries.

def process_json(image):
    #open the file with json
    with open(image) as json_data:
        d = json.load(json_data)

    #Recursive function that outputs each level of the dictionary to a flat directory. Bulk of this function was found via another 
    #programmer in a Google search, but it has been modified so that the flattened output is easier to work with in Pandas
    def flatten_json(y):
        out = {}
        def flatten(x, name='', ind=0):
            if type(x) is dict:
                for a in x:
                    flatten(x[a], name + a + '.', ind)
            elif type(x) is list:
                i = 0
                for a in x:
                    flatten(a, name, ind+i)
                    i += 1
                ind=i
            else:
                out[name[:-1]+'_'+str(ind)] = (x,ind)
        flatten(y)
        return out

    #For this exercise, flatten only the "entry" dictionary. Everything else will be added back in later via some Pandas assignments.
    entry = d['entry']
    flat = flatten_json(entry)

    #Create arrays for data, column names, and indices from the flattened directory
    #Columns and Index arrays will be used to create a blank Pandas dataframe, and then we will iterate through data to fill in the dataframe.
    columns=[]
    data=[]
    index=[]
    for item in flat.items():
        columns.append(item[0].rsplit('_',1)[0])
        data.append(item[1][0])
        index.append(item[1][1])

    #Use the column/index arrays to create a blank pandas df
    output = pd.DataFrame(index=np.unique(index), columns = np.unique(columns))

    #Fill in the individual cells from the data array
    for ind in range(len(index)):
        c = columns[ind]
        i = index[ind]
        output[c].iloc[i] = data[ind]

    #Add the non-entry pieces back
    output['id'] = d['id']
    output['meta.lastUpdated'] = d['meta']['lastUpdated']
    output['resourceType'] = d['resourceType']
    output['type'] = d['type']

    #output to csv (temporary file that will be deleted once the upload to S3 is complete
    try:
        output.to_csv(csv_dir + '/' + 'output.csv', index=False)
    except IOError as e:
        print('Cannot save csv file.')


#Main function that triggers it all
def main():
    create_dirs()
    while True:
        process_images()

if __name__ == "__main__":
    main()
