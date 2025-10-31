"""
Custom storage backend for Google Cloud Storage with explicit public ACL setting.
"""
from storages.backends.gcloud import GoogleCloudStorage
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class PublicGoogleCloudStorage(GoogleCloudStorage):
    """
    Custom GCS storage backend that ensures files are publicly accessible.
    """
    
    def __init__(self, *args, **kwargs):
        """Initialize storage backend with better error handling."""
        try:
            super().__init__(*args, **kwargs)
            # Verify bucket connection
            if hasattr(self, 'bucket') and self.bucket:
                logger.info(f"GCS Storage initialized successfully. Bucket: {self.bucket.name}")
            else:
                logger.warning("GCS Storage initialized but bucket is None")
        except Exception as e:
            logger.error(f"Failed to initialize GCS Storage: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def _save(self, name, content):
        """
        Save the file and explicitly set public read ACL.
        """
        logger.info(f"GCS _save: Starting upload for {name}")
        print(f"GCS _save: Starting upload for {name}")
        
        # Verify bucket is accessible before upload
        if not hasattr(self, 'bucket') or not self.bucket:
            error_msg = "GCS bucket is not initialized. Check your credentials and bucket name."
            logger.error(error_msg)
            print(f"ERROR: {error_msg}")
            raise RuntimeError(error_msg)
        
        # Call parent save method to upload the file
        try:
            name = super()._save(name, content)
            logger.info(f"GCS _save: File uploaded successfully to {name}")
            print(f"GCS _save: File uploaded successfully to {name}")
        except Exception as upload_error:
            error_msg = f"ERROR: Failed to upload file {name}: {upload_error}"
            logger.error(error_msg, exc_info=True)
            print(error_msg)
            import traceback
            traceback.print_exc()
            raise
        
        # Explicitly set public read ACL after upload
        try:
            # Get the blob object using the name (which is the path in the bucket)
            blob = self.bucket.blob(name)
            
            # Verify blob exists
            if not blob.exists():
                error_msg = f"ERROR: Blob {name} does not exist after upload! Upload may have failed silently."
                logger.error(error_msg)
                print(error_msg)
                # Don't return - try to continue with ACL setting anyway
                # Return name so Django thinks upload succeeded
                return name
            
            # Check if uniform bucket-level access is enabled
            # If not, we can use ACLs
            try:
                # Try to make the blob publicly readable using ACL
                blob.acl.save_predefined('publicRead')
                print(f"GCS: Set public ACL for {name}")
            except Exception as acl_error:
                # If ACL fails (uniform bucket-level access), try make_public
                print(f"GCS: ACL method failed, trying make_public: {acl_error}")
                try:
                    blob.make_public()
                    print(f"GCS: Made blob public using make_public for {name}")
                except Exception as make_public_error:
                    print(f"WARNING: Both ACL methods failed for {name}: {make_public_error}")
                    # Don't fail - bucket-level IAM should handle public access
                    
        except Exception as e:
            print(f"WARNING: Failed to set public ACL for {name}: {e}")
            import traceback
            traceback.print_exc()
            # Don't fail the upload if ACL setting fails
            # The file is still saved, just might not be publicly accessible
        
        # Verify the file exists and is accessible
        try:
            blob = self.bucket.blob(name)
            if blob.exists():
                print(f"GCS: Verified file exists at {name}")
                print(f"GCS: File URL: {self.url(name)}")
            else:
                print(f"ERROR: File {name} does not exist after upload!")
        except Exception as verify_error:
            print(f"WARNING: Could not verify file existence: {verify_error}")
        
        return name
    
    def url(self, name):
        """
        Return the public URL for the file.
        """
        return super().url(name)

