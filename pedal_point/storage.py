"""
Custom storage backend for Google Cloud Storage with explicit public ACL setting.
"""
from storages.backends.gcloud import GoogleCloudStorage


class PublicGoogleCloudStorage(GoogleCloudStorage):
    """
    Custom GCS storage backend that ensures files are publicly accessible.
    """
    
    def _save(self, name, content):
        """
        Save the file and explicitly set public read ACL.
        """
        print(f"GCS _save: Starting upload for {name}")
        
        # Call parent save method to upload the file
        try:
            name = super()._save(name, content)
            print(f"GCS _save: File uploaded successfully to {name}")
        except Exception as upload_error:
            print(f"ERROR: Failed to upload file {name}: {upload_error}")
            import traceback
            traceback.print_exc()
            raise
        
        # Explicitly set public read ACL after upload
        try:
            # Get the blob object using the name (which is the path in the bucket)
            blob = self.bucket.blob(name)
            
            # Verify blob exists
            if not blob.exists():
                print(f"WARNING: Blob {name} does not exist after upload!")
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

