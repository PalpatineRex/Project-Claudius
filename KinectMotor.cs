using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using System.Drawing;
using System.Drawing.Imaging;
using Microsoft.Kinect;

class KinectMotor {
    [DllImport("Kinect10.dll")] static extern int NuiCameraElevationSetAngle(int d);

    static KinectSensor sensor = null;

    static void InitSensor(bool withColor) {
        foreach (var s in KinectSensor.KinectSensors)
            if (s.Status == KinectStatus.Connected) { sensor = s; break; }
        if (sensor == null) return;
        try {
            if (withColor)
                sensor.ColorStream.Enable(ColorImageFormat.RgbResolution640x480Fps30);
            sensor.Start();
        } catch (Exception e) {
            Console.Error.WriteLine("ERROR:sensor_start:" + e.Message);
            sensor = null;
        }
    }

    static void Set(int deg) {
        if (deg < -27) deg = -27;
        if (deg >  27) deg =  27;
        NuiCameraElevationSetAngle(deg);
    }

    static void Oui() {
        Set(20);  Thread.Sleep(250); Set(-20); Thread.Sleep(250);
        Set(20);  Thread.Sleep(250); Set(-20); Thread.Sleep(250);
        Set(0);   Thread.Sleep(250);
    }
    static void Non() {
        Set(-27); Thread.Sleep(700); Set(0); Thread.Sleep(200);
        Set(-27); Thread.Sleep(700); Set(0);
    }
    static void Blink() { Set(-10); Thread.Sleep(200); Set(0); Thread.Sleep(200); }
    static void Hello() {
        Set(15); Thread.Sleep(350); Set(0); Thread.Sleep(200);
        Set(15); Thread.Sleep(350); Set(0);
    }
    static void Think() { Set(5); Thread.Sleep(600); Set(-5); Thread.Sleep(600); Set(0); }

    static string Snap(string outDir) {
        if (sensor == null || !sensor.ColorStream.IsEnabled) return "ERROR:no_stream";

        // Drainer 20 frames pour laisser l'auto-exposition s'ajuster, garder la derniere
        ColorImageFrame frame = null;
        for (int i = 0; i < 20; i++) {
            ColorImageFrame f = sensor.ColorStream.OpenNextFrame(150);
            if (f != null) { if (frame != null) frame.Dispose(); frame = f; }
        }
        if (frame == null) return "ERROR:no_frame";

        // Lire Width/Height AVANT Dispose
        int w = frame.Width, h = frame.Height;
        byte[] raw = new byte[frame.PixelDataLength];
        frame.CopyPixelDataTo(raw);
        frame.Dispose();

        // Conversion BGRA->RGB via Marshal.Copy (pas de WriteByte pixel par pixel)
        byte[] rgb = new byte[w * h * 3];
        for (int i = 0; i < w * h; i++) {
            rgb[i * 3]     = raw[i * 4];     // B
            rgb[i * 3 + 1] = raw[i * 4 + 1]; // G
            rgb[i * 3 + 2] = raw[i * 4 + 2]; // R
        }

        string ts     = DateTime.Now.ToString("yyyy-MM-dd-HH-mm-ss");
        string path   = Path.Combine(outDir, "KinectSnap-" + ts + ".png");
        string thumb  = Path.Combine(outDir, "KinectSnap_view-" + ts + ".jpg");

        Bitmap bmp = null;
        Bitmap tmb = null;
        try {
            bmp = new Bitmap(w, h, PixelFormat.Format24bppRgb);
            BitmapData bd = bmp.LockBits(new Rectangle(0, 0, w, h),
                                          ImageLockMode.WriteOnly, PixelFormat.Format24bppRgb);
            // Copier ligne par ligne - IntPtr.Add() requis pour C#5/.NET4
            for (int y = 0; y < h; y++)
                Marshal.Copy(rgb, y * w * 3, IntPtr.Add(bd.Scan0, y * bd.Stride), w * 3);
            bmp.UnlockBits(bd);

            bmp.Save(path, ImageFormat.Png);

            tmb = new Bitmap(bmp, new Size(480, 360));
            tmb.Save(thumb, ImageFormat.Jpeg);
        } finally {
            if (tmb != null) tmb.Dispose();
            if (bmp != null) bmp.Dispose();
        }
        return "OK:" + path;
    }

    static void Main(string[] args) {
        string mode    = args.Length > 0 ? args[0] : "blink";
        string snapDir = args.Length > 1 ? args[1] : @"C:\Users\PC\Pictures";

        bool needColor = (mode == "snap");
        InitSensor(needColor);
        if (needColor) Thread.Sleep(2000); // warm-up expo auto camera

        try {
            if      (mode == "oui")   Oui();
            else if (mode == "non")   Non();
            else if (mode == "blink") Blink();
            else if (mode == "hello") Hello();
            else if (mode == "think") Think();
            else if (mode == "reset") Set(0);
            else if (mode == "snap")  Console.WriteLine(Snap(snapDir));
        } finally {
            if (sensor != null) { sensor.Stop(); sensor.Dispose(); }
        }
    }
}
