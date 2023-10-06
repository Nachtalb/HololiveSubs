import sys
from pathlib import Path
from typing import Dict


def replace_placeholders(template_path: Path, output_path: Path, replacements: Dict[str, str]) -> None:
    content = template_path.read_text()

    for placeholder, value in replacements.items():
        content = content.replace(f"{{{{{placeholder}}}}}", value)

    output_path.write_text(content)


def main() -> None:
    systemd_folder = Path("./systemd")
    user_systemd_folder = Path("~/.config/systemd/user").expanduser()
    current_working_dir = Path.cwd()
    python_executable = sys.executable

    # Make sure the user systemd folder exists
    user_systemd_folder.mkdir(parents=True, exist_ok=True)

    replacements = {"WORKING_DIR": str(current_working_dir), "PYTHON_EXEC": python_executable}

    print("Commands to enable these services:")
    print("systemctl --user daemon-reload")

    new_files = []

    for file_path in sorted(systemd_folder.iterdir()):
        if file_path.suffix == ".template":
            new_file_name = file_path.name.replace(".template", "")
            new_file_path = systemd_folder / new_file_name
            replace_placeholders(file_path, new_file_path, replacements)
            new_files.append(new_file_path)
            print(f"ln -s {new_file_path.absolute()} {user_systemd_folder}")

    for new_file_path in new_files:
        print(f"systemctl --user enable --now {new_file_path.name}")


if __name__ == "__main__":
    main()
