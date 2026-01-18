def get_file_category(file_path: str, language: str) -> str:
    if language != "unknown":
        return "CODE"

    if '.' not in file_path:
        extension = file_path.split('/')[-1].lower()
    else:
        extension = file_path.split('.')[-1].lower()

    return f".{extension}"
