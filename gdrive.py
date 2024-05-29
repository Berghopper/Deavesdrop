import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

# app-only file access
SCOPES = ["https://www.googleapis.com/auth/drive.file"]


class GoogleDriveUploader:
    def __init__(self, secret_file, token_file=None):
        self.service, self.creds = GoogleDriveUploader.build_service(
            secret_file, token_file
        )

    def build_service(secret_file, token_file=None) -> tuple[Resource, Credentials]:
        creds = None
        if token_file and os.path.exists(token_file):
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(secret_file, SCOPES)
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run if token_file is provided
            if token_file:
                with open(token_file, "w") as token:
                    token.write(creds.to_json())
        return build("drive", "v3", credentials=creds), creds

    def check_if_file_exists(self, file_name, g_folder_id):
        # Check if file exists in the folder
        query = f"name='{file_name}' and '{g_folder_id}' in parents"
        response = self.service.files().list(q=query).execute()
        files = response.get("files", [])
        return len(files) > 0

    def upload_resumable(self, file_path, g_folder_id):
        file_name = os.path.basename(file_path)

        metadata = {
            "name": file_name,
            "parents": [g_folder_id],
        }

        try:
            media_body = MediaFileUpload(file_path, resumable=True)
            file = (
                self.service.files()
                .create(body=metadata, media_body=media_body)
                .execute()
            )
            return file.get("id")
        except HttpError as error:
            return None
