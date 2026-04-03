#!/usr/bin/env python3
import os
import sys

def lighten_file(filepath, target_chars=800000):
    if not os.path.exists(filepath):
        print(f"Error: {filepath} not found.")
        return

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original_size = len(content)
    print(f"Original size: {original_size} characters.")

    # 1. Remove form feed characters
    content = content.replace('\f', '')

    # 2. Process lines
    lines = content.splitlines()
    new_lines = []
    
    for line in lines:
        stripped = line.strip()
        if stripped:
            new_lines.append(stripped)
    
    # Join with single newline
    lightened_content = '\n'.join(new_lines)
    
    new_size = len(lightened_content)
    print(f"Size after stripping and removing empty lines: {new_size} characters.")

    # 3. Truncate if still over target
    if new_size > target_chars:
        print(f"Still over target {target_chars}. Truncating...")
        lightened_content = lightened_content[:target_chars]
        new_size = len(lightened_content)
        print(f"Final size after truncation: {new_size} characters.")

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(lightened_content)

    print(f"Success! Saved lightened file to {filepath}.")

if __name__ == "__main__":
    path = "/home/Projects/NH-Mini/sviluppi/dias/data/projects/dan-simmons-hyperion/source/Dan Simmons - Hyperion.pdf.txt"
    lighten_file(path)
