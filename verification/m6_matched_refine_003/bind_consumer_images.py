"""Bind existing rendered PNG bytes to the consumer case's permitted image directory."""

from pathlib import Path
import shutil
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write


def main():
    started, cpu = time.perf_counter(), time.process_time()
    case = HERE / "private/consumer_cases/matched"
    history = HERE / "private/input_path_preflight"
    history.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(case / "task.json", history / "ORIGINAL_TASK.json")
    shutil.copyfile(HERE / "IMAGE_BINDING.json", history / "ORIGINAL_IMAGE_BINDING.json")
    images = case / "images"
    images.mkdir(exist_ok=False)
    task, binding = read(case / "task.json"), read("IMAGE_BINDING.json")
    records = []
    for row in task["images"]:
        original = Path(row["path"])
        destination = images / original.name
        shutil.copyfile(original, destination)
        if identity(destination)["sha256"] != row["sha256"]:
            raise ValueError("consumer_image_copy_changed_bytes")
        row["path"] = str(destination)
        records.append(dict(source=identity(original), delivery=identity(destination)))
    write((case / "task.json").relative_to(HERE), task)
    binding["images"] = task["images"]
    binding["public_task"] = identity(case / "task.json")
    binding["consumer_path_binding"] = "IMAGE_PATH_PREFLIGHT.json"
    write("IMAGE_BINDING.json", binding)
    write("IMAGE_PATH_PREFLIGHT.json", dict(status="pass", image_copies=records,
        issue="Static integration found images under construction case rather than permitted consumer case directory",
        actual_images_regenerated=0, additional_Blender=0, additional_Pro=0,
        wall_s=time.perf_counter() - started, cpu_s=time.process_time() - cpu))
    print("eight exact image copies bound to consumer case", flush=True)


if __name__ == "__main__":
    main()
