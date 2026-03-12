using System;
using System.IO;
using System.Threading;
using System.Drawing;
using System.Drawing.Imaging;
using Microsoft.Kinect;

class KinectSnap {
    static void Main(string[] args) {
        string outDir = args.Length > 0 ? args[0] : @"C:\Users\PC\Pictures";
        KinectSensor sensor = null;

        foreach (var s in KinectSensor.KinectSensors) {
            if (s.Status == KinectStatus.Connected) { sensor = s; break; }
        }
        if (sensor == null) { Console.WriteLine("ERROR:no_sensor"); return; }

        sensor.ColorStream.Enable(ColorImageFormat.RgbResolution640x480Fps30);
        sensor.Start();
        Thread.Sleep(500); // laisse le flux s initialiser

        ColorImageFrame frame = null;
        for (int i = 0; i < 30; i++) {
            frame = sensor.ColorStream.OpenNextFrame(100);
            if (frame != null) break;
        }
        if (frame == null) { Console.WriteLine("ERROR:no_frame"); sensor.Stop(); return; }

        byte[] data = new byte[frame.PixelDataLength];
        frame.CopyPixelDataTo(data);

        Bitmap bmp = new Bitmap(frame.Width, frame.Height, PixelFormat.Format32bppRgb);
        BitmapData bmpData = bmp.LockBits(
            new Rectangle(0, 0, bmp.Width, bmp.Height),
            ImageLockMode.WriteOnly, PixelFormat.Format32bppRgb
        );
        System.Runtime.InteropServices.Marshal.Copy(data, 0, bmpData.Scan0, data.Length);
        bmp.UnlockBits(bmpData);

        string ts = DateTime.Now.ToString("yyyy-MM-dd-HH-mm-ss");
        string path = Path.Combine(outDir, "KinectSnap-" + ts + ".png");
        bmp.Save(path, ImageFormat.Png);

        frame.Dispose();
        sensor.Stop();
        Console.WriteLine("OK:" + path);
    }
}
