Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "<INSTALL_DIR>"
sh.Run "cmd /c ""<INSTALL_DIR>\start-napcat.bat""", 0, False
