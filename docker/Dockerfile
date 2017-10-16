FROM ubuntu:16.04

RUN apt-get update
RUN apt-get install -y python3 python3-pip
RUN pip3 install awscli boto3 pandas

ADD ProcessJson.py /

CMD ["python3","-u","/ProcessJson.py"]
