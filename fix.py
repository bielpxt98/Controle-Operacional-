import sys
with open('app.py', 'r', encoding='utf-8') as f:
    text = f.read()

# find first @app.route("/whatsapp")
idx1 = text.find('@app.route("/whatsapp")')
# find second @app.route("/whatsapp")
idx2 = text.find('@app.route("/whatsapp")', idx1 + 1)
# find if __name__ == "__main__":
idx3 = text.find('if __name__ == "__main__":', idx2)

# keep text before idx2, and after idx3
new_text = text[:idx2] + text[idx3:]
with open('app.py', 'w', encoding='utf-8') as f:
    f.write(new_text)
