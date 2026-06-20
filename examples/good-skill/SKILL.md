---
name: good-skill
description: Use when the user wants to read, merge, split, or extract text from PDF files, or mentions a .pdf by name.
version: 1.0.0
---

# PDF Tools

Use the `pdftk` CLI to operate on PDF files.

1. To merge: `pdftk a.pdf b.pdf cat output merged.pdf`.
2. To extract text: `pdftotext input.pdf out.txt`.

## How to verify

Run `pdftk --version` to confirm the tool is installed before proceeding.
