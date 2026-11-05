using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;

[assembly: AssemblyTitle("App Video Chia Sẻ Hội Thoại 2 Người")]
[assembly: AssemblyProduct("App Video Chia Sẻ Hội Thoại 2 Người")]
[assembly: AssemblyVersion("1.2.0.0")]

class Program {
    [STAThread]
    static void Main(string[] args) {
        string appDir = AppDomain.CurrentDomain.BaseDirectory;
        string pyw = @"C:\Users\Dung\AppData\Local\Programs\Python\Python311\pythonw.exe";
        if (!File.Exists(pyw)) {
            pyw = "pythonw.exe";
        }
        string script = Path.Combine(appDir, "desktop_app.py");
        ProcessStartInfo psi = new ProcessStartInfo();
        psi.FileName = pyw;
        psi.Arguments = "\"" + script + "\"";
        psi.WorkingDirectory = appDir;
        psi.UseShellExecute = false;
        psi.CreateNoWindow = true;
        Process.Start(psi);
    }
}