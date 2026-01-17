def get_file_category(file_path: str, language: str) -> str:
    if language != "unknown":
        return "CODE"

    if '.' not in file_path:
        extension = file_path.split('/')[-1].lower()
    else:
        extension = file_path.split('.')[-1].lower()

    return f".{extension}"


def format_file_path_with_chunk(file_path: str, chunk_index: int) -> str:
    return f"{file_path}#{chunk_index}"
