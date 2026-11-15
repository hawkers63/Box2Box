// Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
// Not to be copied or altered without express permission. See LICENSE.
//
// Box2Box.exe starts Box2Box with the project's own Python, as Box2Box.bat does, and carries the
// Box2Box icon. Build it with build_launcher.ps1. Drop a save onto it to open that save.

using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;
using System.Windows.Forms;

[assembly: AssemblyTitle("Box2Box")]
[assembly: AssemblyProduct("Box2Box")]
[assembly: AssemblyDescription("Starts Box2Box, a viewer for Football Manager saves")]
[assembly: AssemblyCopyright("Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.")]

static class Launcher
{
    [STAThread]
    static int Main(string[] args)
    {
        string folder = AppDomain.CurrentDomain.BaseDirectory;
        string app = Path.Combine(folder, "fm_review.py");
        string python = Path.Combine(folder, @".venv\Scripts\pythonw.exe");
        if (!File.Exists(app))
        {
            return Complain("Box2Box.exe must stay in the Box2Box folder, beside fm_review.py.\n\n"
                + "To start Box2Box from anywhere else, such as the desktop, use a shortcut to it: "
                + "build_launcher.ps1 puts one on the desktop.");
        }
        if (!File.Exists(python))
        {
            return Complain("The Python environment is missing. In " + folder.TrimEnd('\\') + ", run:\n\n"
                + "    py -3.14 -m venv .venv\n"
                + "    .venv\\Scripts\\python -m pip install -r requirements.txt");
        }
        string arguments = Quote(app);
        if (args.Length > 0)
        {
            arguments += " " + Quote(args[0]);      // Box2Box opens one save at a time
        }
        var start = new ProcessStartInfo(python, arguments);
        start.WorkingDirectory = folder;
        start.UseShellExecute = false;
        try
        {
            Process.Start(start);
        }
        catch (Exception problem)
        {
            return Complain("Box2Box could not be started:\n\n" + problem.Message);
        }
        return 0;
    }

    static int Complain(string message)
    {
        MessageBox.Show(message, "Box2Box", MessageBoxButtons.OK, MessageBoxIcon.Warning);
        return 1;
    }

    // One argument, quoted so that the C runtime reads it back unchanged.
    static string Quote(string value)
    {
        var quoted = new StringBuilder("\"");
        int slashes = 0;
        foreach (char c in value)
        {
            if (c == '\\') { slashes++; continue; }
            quoted.Append('\\', c == '"' ? slashes * 2 + 1 : slashes);
            slashes = 0;
            quoted.Append(c);
        }
        return quoted.Append('\\', slashes * 2).Append('"').ToString();
    }
}
