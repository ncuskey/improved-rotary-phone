#!/usr/bin/env python3
# Download the helper library from https://www.twilio.com/docs/python/install
import os
from twilio.rest import Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Find your Account SID and Auth Token at twilio.com/console
# and set the environment variables. See http://twil.io/secure
account_sid = os.environ["TWILIO_ACCOUNT_SID"]
auth_token = os.environ["TWILIO_AUTH_TOKEN"]
client = Client(account_sid, auth_token)

message = client.messages.create(
    body="BookFinder scraper test message!",
    from_=os.environ["TWILIO_PHONE_NUMBER"],
    to=os.environ["YOUR_PHONE_NUMBER"],
)

print(f"Message sent! SID: {message.sid}")
print(f"Status: {message.status}")
