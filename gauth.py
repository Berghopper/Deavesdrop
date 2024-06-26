import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import dotenv_values

config = dotenv_values(".env")

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

GDRIVE_SECRETS_DIR = config["GDRIVE_SECRETS_DIR"]


def main():
    """
    Authenticate with Google Drive API.
    """
    creds = None
    if os.path.exists(f"{GDRIVE_SECRETS_DIR}/token.json"):
        creds = Credentials.from_authorized_user_file(
            f"{GDRIVE_SECRETS_DIR}/token.json", SCOPES
        )
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                f"{GDRIVE_SECRETS_DIR}/secret.json", SCOPES
            )
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(f"{GDRIVE_SECRETS_DIR}/token.json", "w") as token:
            token.write(creds.to_json())

    try:
        build("drive", "v3", credentials=creds)
        print("Successfully authenticated with Google Drive API.")
    except HttpError as error:
        print(f"An error occurred: {error}")


if __name__ == "__main__":
    main()
