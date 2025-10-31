import os
import django
from django.core.files.storage import default_storage

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

def upload_directory_to_s3(local_path, s3_path=""):
    """Рекурсивно загружает папку в S3"""
    for root, dirs, files in os.walk(local_path):
        for file in files:
            local_file_path = os.path.join(root, file)
            
            # Создаем S3 путь
            relative_path = os.path.relpath(local_file_path, local_path)
            s3_file_path = os.path.join(s3_path, relative_path).replace("\\", "/")
            
            print(f"Uploading: {local_file_path} -> {s3_file_path}")
            
            # Загружаем файл в S3
            with open(local_file_path, 'rb') as f:
                default_storage.save(s3_file_path, f)

if __name__ == "__main__":
    backup_dir = "_media_backup_2025-10-30_1226"
    
    if os.path.exists(backup_dir):
        print("Начинаем перенос медиафайлов в S3...")
        upload_directory_to_s3(backup_dir)
        print("Перенос завершен!")
    else:
        print("Папка с бэкапом не найдена")