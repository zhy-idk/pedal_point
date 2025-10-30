# Google Cloud Storage Setup Guide

This guide will help you set up Google Cloud Storage for handling media files in your Django application.

## Prerequisites

- Google Cloud Platform account
- Project created in GCP Console
- Billing enabled on your project

## Step 1: Create a GCS Bucket

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Navigate to **Cloud Storage** > **Buckets**
3. Click **Create Bucket**
4. Configure your bucket:
   - **Name**: Choose a globally unique name (e.g., `pedal-point-media`)
   - **Location type**: Choose based on your needs
     - `Multi-region` for global access
     - `Region` for better performance in specific location
   - **Storage class**: `Standard` (recommended for frequently accessed files)
   - **Access control**: Choose **Fine-grained** (recommended)
   - **Public access**: Enable if you want direct public access to images
5. Click **Create**

## Step 2: Create a Service Account

1. Go to **IAM & Admin** > **Service Accounts**
2. Click **Create Service Account**
3. Enter details:
   - **Name**: `pedal-point-storage` (or your preferred name)
   - **Description**: "Service account for Pedal Point media storage"
4. Click **Create and Continue**
5. Grant permissions:
   - Add role: **Storage Object Admin** (for full read/write access)
   - Or **Storage Object Creator** (for upload only)
6. Click **Continue** then **Done**

## Step 3: Generate Service Account Key

1. Find your newly created service account in the list
2. Click on it to open details
3. Go to the **Keys** tab
4. Click **Add Key** > **Create new key**
5. Select **JSON** format
6. Click **Create**
7. The JSON key file will download automatically
8. **IMPORTANT**: Store this file securely - it contains credentials

## Step 4: Configure Django Settings

### Option 1: Using Environment Variables (Recommended for Production)

Add these to your `.env` file:

```env
USE_GCS=True
GS_BUCKET_NAME=pedal-point-media
GS_PROJECT_ID=your-project-id
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
```

### Option 2: For Render/Heroku Deployment

1. Upload your service account JSON to your deployment platform
2. Set environment variables in your deployment dashboard:
   - `USE_GCS=True`
   - `GS_BUCKET_NAME=your-bucket-name`
   - `GS_PROJECT_ID=your-project-id`
   - `GOOGLE_APPLICATION_CREDENTIALS=/opt/render/project/src/service-account.json`

Or, you can encode the JSON as a single environment variable:

```env
USE_GCS=True
GS_BUCKET_NAME=your-bucket-name
GS_PROJECT_ID=your-project-id
GCS_CREDENTIALS_JSON={"type":"service_account","project_id":"..."}
```

Then update `settings.py` to parse the JSON:

```python
import json

if USE_GCS:
    GS_CREDENTIALS_JSON = os.getenv("GCS_CREDENTIALS_JSON")
    if GS_CREDENTIALS_JSON:
        from google.oauth2 import service_account
        GS_CREDENTIALS = service_account.Credentials.from_service_account_info(
            json.loads(GCS_CREDENTIALS_JSON)
        )
```

## Step 5: Install Dependencies

```bash
pip install -r requirements.txt
```

This will install:
- `django-storages==1.14.4`
- `google-cloud-storage==2.18.2`

## Step 6: Make Bucket Public (Optional)

If you want images to be publicly accessible:

1. Go to your bucket in GCS Console
2. Click **Permissions** tab
3. Click **Grant Access**
4. Add principal: `allUsers`
5. Role: **Storage Object Viewer**
6. Click **Save**

**OR** set permissions via command line:

```bash
gsutil iam ch allUsers:objectViewer gs://your-bucket-name
```

## Step 7: Test the Setup

### Local Testing

1. Create a `.env` file in `pedal_point/` directory:
```env
USE_GCS=True
GS_BUCKET_NAME=your-bucket-name
GS_PROJECT_ID=your-project-id
GOOGLE_APPLICATION_CREDENTIALS=./service-account-key.json
```

2. Place your service account JSON file in the `pedal_point/` directory

3. Run your Django server:
```bash
python manage.py runserver
```

4. Upload an image through the admin panel or frontend

5. Check your GCS bucket - the file should appear there

6. The image URL should be: `https://storage.googleapis.com/your-bucket-name/path/to/file.jpg`

### Production Testing

1. Set environment variables in your hosting platform (Render, Heroku, etc.)
2. Deploy your application
3. Upload an image
4. Verify it appears in GCS bucket
5. Verify the URL is accessible

## Troubleshooting

### "No module named 'google.cloud'"
- Run: `pip install google-cloud-storage`

### "Could not automatically determine credentials"
- Ensure `GOOGLE_APPLICATION_CREDENTIALS` points to valid JSON file
- For local development: Use absolute path
- For production: Ensure file is uploaded with your deployment

### "Access Denied" when accessing images
- Make bucket public (see Step 6)
- Or ensure `GS_DEFAULT_ACL = "publicRead"` is set in settings

### "Bucket not found"
- Verify `GS_BUCKET_NAME` matches your actual bucket name
- Check for typos in environment variables

### Files uploaded but URLs not working
- Ensure bucket has public access
- Check CORS settings if accessing from browser
- Verify `MEDIA_URL` is set correctly

## CORS Configuration (if needed)

If you're accessing files from a different domain, add CORS policy to your bucket:

1. Create a `cors.json` file:
```json
[
  {
    "origin": ["https://your-frontend-domain.com"],
    "method": ["GET", "HEAD"],
    "responseHeader": ["Content-Type"],
    "maxAgeSeconds": 3600
  }
]
```

2. Apply CORS policy:
```bash
gsutil cors set cors.json gs://your-bucket-name
```

## Cost Optimization

- **Storage**: ~$0.02 per GB/month for Standard class
- **Operations**: Free tier includes significant operations
- **Data transfer**: First 1GB free/month, then ~$0.12/GB

### Tips:
1. Use **lifecycle rules** to automatically delete old files
2. Choose **Nearline** or **Coldline** for infrequently accessed files
3. Enable **compression** for text files
4. Use **CDN** for high-traffic applications

## Security Best Practices

1. **Never commit** service account JSON to git
2. Add to `.gitignore`:
   ```
   service-account*.json
   *.json
   .env
   ```
3. Use **least privilege** - only grant necessary permissions
4. **Rotate keys** regularly
5. Use **Workload Identity** for GKE deployments (most secure)

## Migration from Local Storage

To migrate existing media files to GCS:

```bash
# Install gsutil
# Then sync your local media folder to GCS
gsutil -m rsync -r ./media gs://your-bucket-name/media
```

Or use Django management command:

```python
from django.core.management.base import BaseCommand
from django.core.files.storage import default_storage
import os

class Command(BaseCommand):
    def handle(self, *args, **options):
        # Copy files from local to GCS
        for root, dirs, files in os.walk('media'):
            for file in files:
                local_path = os.path.join(root, file)
                gcs_path = local_path.replace('media/', '')
                with open(local_path, 'rb') as f:
                    default_storage.save(gcs_path, f)
```

## Switching Between Local and GCS

Toggle between local and cloud storage by changing the `USE_GCS` environment variable:

- **Development**: `USE_GCS=False` (uses local media folder)
- **Production**: `USE_GCS=True` (uses Google Cloud Storage)

This allows you to develop locally without GCS costs and deploy to production with cloud storage.

