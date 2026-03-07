p = r"C:\Users\Roberto\Desktop\Avvia_Tutti_Server_ARIA.bat"
with open(p, "r", encoding="utf-8") as f:
    c = f.read()

if "sox-14" not in c:
    c = c.replace(
        r"set MINICONDA_ROOT=C:\Users\Roberto\miniconda3",
        "set MINICONDA_ROOT=C:\\Users\\Roberto\\miniconda3\nset PATH=C:\\Users\\Roberto\\aria\\envs\\sox\\sox-14.4.2;%PATH%"
    )
    with open(p, "w", encoding="utf-8") as f:
        f.write(c)
    print("PATCHED")
else:
    print("ALREADY_PATCHED")
