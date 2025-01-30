#from line_profiler import LineProfiler

import requests
import tarfile
import os
import io
import time
import sys
import re
from collections import defaultdict

GITHUB_TOKEN = open("token.txt", "r").read()
GITHUB_API_URL = "https://api.github.com"

EXTENSION_TO_LANGUAGE = {
    ".bat": "Batch",
    ".py": "Python",
    ".cpp": "C++",
    ".cbot": "CBot",
    ".hh": "C++",
    ".cxx": "C++",
    ".hxx": "C++",
    ".gd": "Godot Script",
    ".cmake": "CMake",
    ".hlsl": "HLSL",
    ".hlsli": "HLSL",
    ".h": "C",
    ".inl": "C++",
    ".c++": "C++",
    ".hpp": "C++",
    ".cc": "C++",
    ".inc": "C++",
    ".tpp": "C++",
    ".ispc": "Intel SPMD Program",
    ".lua": "Lua",
    ".ps1": "PowerShell",
    ".c": "C",
    ".C": "C",
    ".3": "Manual page",
    ".cs": "C#",
    ".java": "Java",
    ".js": "JavaScript",
    ".tsx": "TypeScript XML",
    ".ts": "TypeScript",
    ".html": "HTML",
    ".css": "CSS",
    ".go": "Go",
    ".rb": "Ruby",
    ".php": "PHP",
    ".rs": "Rust",
    ".swift": "Swift",
    ".m": "Objective-C",
    ".kt": "Kotlin",
    ".sh": "Shell Script",
    # ".xml": "XML",
    #".json": "JSON",
    #".yml": "YAML",
    # ".md": "Markdown",
    ".usf": "Unreal Shader File",
    ".ush": "Unreal Shader Header",
    ".mm": "Objective-C++",
    ".glsl": "OpenGL Shader File",
    ".dart": "Dart",
    ".pl": "Perl",
    ".sc": "BGFX Compiled Shader",
    ".hpp11": "C++",
    ".bf": "Brainfuck",
    ".zig": "Zig",
    ".d": "D"
}

IGNORE_LIST = [
    ".ttf",
    ".gif",
    ".drp",
    ".dylib",
    ".lib",
    ".TXT",
    ".xml",
    ".vcproj",
    ".vcxproj",
    ".dylib",
    ".so",
    ".json",
    ".lib",
    ".exe",
    ".cal",
    ".dll",
    ".txt",
    ".png",
    ".filters",
    ".resx",
    ".udn",
    ".ini",
    ".def",
    ".mk",
    ".uplugin",
    ".in",
    ".isph",
    ".sln",
    ".yaml",
    ".yml",
    ".csproj",
    ".xml",
    ".rc",
    ".am",
    ".tps",
    ".dsp",
    ".template",
    ".replay",
    ".XML",
    ".command",
    ".snippet",
    ".config",
    ".patch",
    ".exp",
    ".jpg",
    ".uproject",
    ".storyboard",
    ".windows",
    ".sgi",
    ".strings",
]

cpp_keywords = {
    "class",
    "namespace",
    "template",
    "public",
    "private",
    "protected",
    "virtual",
    "inline",
    "new",
    "delete",
    "try",
    "catch",
    "throw",
    "using",
    "friend",
    "this",
    "operator",
    "export",
    "explicit",
    "mutable",
    "static_cast",
    "dynamic_cast",
    "const_cast",
    "reinterpret_cast",
    "wchar_t",
    "nullptr",
    "override",
    "final",
    "constexpr",
    "decltype",
    "typeid",
    "typename",
    "static_assert",
    "noexcept",
    "thread_local",
    ".cpp"
}

cpp_includes = {
    "<string>",
    "<vector>",
    "<iostream>",
    "<memory>",
    "<map>",
    "<unordered_map>",
    "<set>",
    "<deque>",
    "<list>",
    "<utility>",
    "<algorithm>",
    "<functional>",
    "<type_traits>",
}

c_keywords = {}

import re

# profiler = LineProfiler()

def strip_comments(content):
    """
    Remove both single-line (//) and multiline (/* */) comments from the code.
    """
    pattern = r"//.*?$|/\*.*?\*/"  # Match // to the end of the line OR /* ... */
    stripped_content = re.sub(pattern, "", content, flags=re.DOTALL | re.MULTILINE)
    return stripped_content

def is_cpp_header(file_obj):
    """
    Check if a .h file is likely a C++ header.
    Criteria:
      1. Contains specific C++ keywords like class, namespace, etc.
      2. Uses #include with <> and filenames without a .h extension.
    """

    try:
        # Read file content
        content = file_obj.read().decode("utf-8", errors="ignore")

        # Remove comments from the content
        stripped_content = strip_comments(content)

        includes = [line.strip() for line in stripped_content.splitlines() if line.startswith("#include")]
        for include in includes:
            if any(cpp_header in include for cpp_header in cpp_includes):
                return True
            # Detect #include "file.h" style includes
            if '"' in include and include.endswith('.h"'):
                return True

        # Check for C++ keywords
        if any(keyword in stripped_content for keyword in cpp_keywords):
            return True
        elif any(keyword in stripped_content for keyword in c_keywords):
            return False

        return False
    except Exception as e:
        print(f"Error reading file: {e}")
        return False

# @profiler
def is_binary(file_stream):
    """Detect if the file is binary by analyzing the content."""

    block_size = 24
    file_content = file_stream.read(block_size)
    if not file_content:
        return False

    text_characters = bytearray(range(32, 127)) + b'\n\t\r'
    non_text_ratio = sum(byte not in text_characters for byte in file_content) / len(file_content)

    return non_text_ratio

def stream_repo_tarball(owner, repo):
    """Stream the tarball of the repository."""

    headers = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
    url = f"{GITHUB_API_URL}/repos/{owner}/{repo}/tarball"
    response = requests.get(url, headers=headers, stream=True)
    response.raise_for_status()

    print("Downloaded repository!                     ")
    print()

    return response.raw

# @profiler
def count_lines_and_map_languages(tar_stream):
    """Count lines and map file extensions to languages in a streamed tarball."""

    starttime = time.time()
    total_lines = 0
    processed_files = 0
    total_files = 0
    ignored_files = 0
    language_lines = defaultdict(int)
    other_extensions = defaultdict(int)

    with tarfile.open(fileobj=tar_stream, mode="r|gz") as tar:
        for member in tar:
            if member.isfile():
                file_extension = os.path.splitext(member.name)[1]
                language = EXTENSION_TO_LANGUAGE.get(file_extension, "Other")

                if not file_extension or file_extension in IGNORE_LIST:
                    ignored_files += 1
                    continue

                file_obj = tar.extractfile(member)
                if file_obj is not None:
                    if is_binary(file_obj):
                        ignored_files += 1
                        continue

                    try:
                        if file_extension == ".h":
                            if is_cpp_header(file_obj):
                                language = "C++"
                            else:
                                language = "C"
                        lines = file_obj.read().decode("utf-8", errors="ignore").splitlines()
                        line_count = len(lines)

                        if language == "Other":
                            other_extensions[file_extension] += line_count
                        else:
                            total_lines += line_count
                            language_lines[language] += line_count
                            processed_files += 1

                        sys.stdout.write('\033[2K\033[1G')
                        print(f"{processed_files} files. "
                              f"Lines: {total_lines:,} ({member.name.split('/')[-1]} - {language})", end="\r")
                    except Exception as e:
                        print(f"\nSkipped {member.name} due to error: {e}")
    endtime = time.time()
    print(f"\nCounted {processed_files + ignored_files:,} files in {round(endtime - starttime, 2)} seconds.")
    print(f"{round(total_lines, 2) / round(endtime - starttime, 2)} lines/second")

    return total_lines, language_lines, other_extensions

def get_largest_other_extensions(other_extensions):
    """Get the largest file extensions under 'Other'."""

    largest_extensions = sorted(other_extensions.items(), key=lambda x: -x[1])
    return largest_extensions[:15]

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: py main.py owner repo")
        sys.exit()

    owner = sys.argv[1]
    repo = sys.argv[2]

    try:
        print("Downloading repository tarball in chunks...", end="\r")
        tar_stream = stream_repo_tarball(owner, repo)
        total_lines, language_lines, other_extensions = count_lines_and_map_languages(tar_stream)

        print(f"\nTotal lines of code in {owner}/{repo}: {total_lines:,}\n")
        print("Lines of code by language:")
        for language, lines in sorted(language_lines.items(), key=lambda x: -x[1]):
            percentage = round((lines / total_lines) * 100, 2)
            print(f"  {language}: {lines:,} ({percentage}%)")

        largest_other_extensions = get_largest_other_extensions(other_extensions)
        if largest_other_extensions:
            print("\nLargest file extensions under 'Other':")
            for ext, lines in largest_other_extensions:
                print(f"  {ext}: {lines} lines")

    except requests.exceptions.RequestException as e:
        print(f"\nError: {e}")

    # profiler.print_stats()