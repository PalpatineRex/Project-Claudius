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
    static string dataDir = null;

    // --- Presence config (defaults, overridden by presence_config.txt) ---
    static int presenceMinMm   = 500;   // ignore closer (noise)
    static int presenceMaxMm   = 1500;  // detection zone max
    static int presencePixelThreshold = 800;  // min pixels in zone to trigger
    static int presenceScanMs  = 500;   // scan interval ms
    static int presenceCooldownS = 30;  // seconds between presence triggers

    // --- Paths ---
    static string MotorCmdFile  { get { return Path.Combine(dataDir, "motor_cmd.txt"); } }
    static string PresenceFile  { get { return Path.Combine(dataDir, "presence.txt"); } }
    static string ConfigFile    { get { return Path.Combine(dataDir, "presence_config.txt"); } }
    static string LogFile       { get { return Path.Combine(dataDir, "kinect.log"); } }

    static void Log(string msg) {
        string line = "[MOTOR " + DateTime.Now.ToString("HH:mm:ss") + "] " + msg;
        Console.WriteLine(line);
        try { File.AppendAllText(LogFile, line + "\n"); } catch {}
    }

    static void InitSensor(bool withColor, bool withDepth) {
        foreach (var s in KinectSensor.KinectSensors)
            if (s.Status == KinectStatus.Connected) { sensor = s; break; }
        if (sensor == null) return;
        try {
            if (withColor)
                sensor.ColorStream.Enable(ColorImageFormat.RgbResolution640x480Fps30);
            if (withDepth)
                sensor.DepthStream.Enable(DepthImageFormat.Resolution320x240Fps30);
            sensor.Start();
        } catch (Exception e) {
            Console.Error.WriteLine("ERROR:sensor_start:" + e.Message);
            sensor = null;
        }
    }

    static void StopSensor() {
        if (sensor != null) {
            try { sensor.Stop(); sensor.Dispose(); } catch {}
            sensor = null;
        }
    }

    // --- Motor gestures ---
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

    static void RunGesture(string cmd) {
        switch (cmd) {
            case "oui":   Oui();   break;
            case "non":   Non();   break;
            case "blink": Blink(); break;
            case "hello": Hello(); break;
            case "think": Think(); break;
            case "reset": Set(0);  break;
            default: Log("unknown gesture: " + cmd); break;
        }
    }

    // --- Snap ---
    static string Snap(string outDir) {
        if (sensor == null) return "ERROR:no_sensor";
        if (!sensor.ColorStream.IsEnabled) {
            try { sensor.ColorStream.Enable(ColorImageFormat.RgbResolution640x480Fps30); }
            catch { return "ERROR:color_enable"; }
            Thread.Sleep(2000);
        }

        ColorImageFrame frame = null;
        for (int i = 0; i < 20; i++) {
            ColorImageFrame f = sensor.ColorStream.OpenNextFrame(150);
            if (f != null) { if (frame != null) frame.Dispose(); frame = f; }
        }
        if (frame == null) return "ERROR:no_frame";

        int w = frame.Width, h = frame.Height;
        byte[] raw = new byte[frame.PixelDataLength];
        frame.CopyPixelDataTo(raw);
        frame.Dispose();

        byte[] rgb = new byte[w * h * 3];
        for (int i = 0; i < w * h; i++) {
            rgb[i * 3]     = raw[i * 4];
            rgb[i * 3 + 1] = raw[i * 4 + 1];
            rgb[i * 3 + 2] = raw[i * 4 + 2];
        }

        string ts    = DateTime.Now.ToString("yyyy-MM-dd-HH-mm-ss");
        string path  = Path.Combine(outDir, "KinectSnap-" + ts + ".png");
        string thumb = Path.Combine(outDir, "KinectSnap_view-" + ts + ".jpg");

        Bitmap bmp = null, tmb = null;
        try {
            bmp = new Bitmap(w, h, PixelFormat.Format24bppRgb);
            BitmapData bd = bmp.LockBits(new Rectangle(0, 0, w, h),
                                          ImageLockMode.WriteOnly, PixelFormat.Format24bppRgb);
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

    // --- Presence detection ---
    static void LoadPresenceConfig() {
        try {
            if (!File.Exists(ConfigFile)) {
                File.WriteAllText(ConfigFile,
                    "# Presence detection config\n" +
                    "# Distance min/max in mm (Kinect v1 range: 800-4000)\n" +
                    "min_mm=500\n" +
                    "max_mm=1500\n" +
                    "# Min depth pixels in zone to trigger presence\n" +
                    "pixel_threshold=800\n" +
                    "# Scan interval in ms\n" +
                    "scan_ms=500\n" +
                    "# Cooldown between presence triggers (seconds)\n" +
                    "cooldown_s=30\n"
                );
                Log("Config par defaut ecrite: " + ConfigFile);
                return;
            }
            foreach (string line in File.ReadAllLines(ConfigFile)) {
                string l = line.Trim();
                if (l.StartsWith("#") || !l.Contains("=")) continue;
                string[] parts = l.Split(new char[]{'='}, 2);
                string key = parts[0].Trim().ToLower();
                int val;
                if (!int.TryParse(parts[1].Trim(), out val)) continue;
                switch (key) {
                    case "min_mm":          presenceMinMm = val; break;
                    case "max_mm":          presenceMaxMm = val; break;
                    case "pixel_threshold": presencePixelThreshold = val; break;
                    case "scan_ms":         presenceScanMs = Math.Max(100, val); break;
                    case "cooldown_s":      presenceCooldownS = Math.Max(5, val); break;
                }
            }
            Log(string.Format("Config: {0}-{1}mm, seuil={2}px, scan={3}ms, cooldown={4}s",
                presenceMinMm, presenceMaxMm, presencePixelThreshold, presenceScanMs, presenceCooldownS));
        } catch (Exception e) {
            Log("ERR config: " + e.Message);
        }
    }

    static int AnalyzeDepthFrame() {
        if (sensor == null || !sensor.DepthStream.IsEnabled) return -1;
        DepthImageFrame frame = null;
        try {
            frame = sensor.DepthStream.OpenNextFrame(200);
            if (frame == null) return -1;
            short[] depthData = new short[frame.PixelDataLength];
            frame.CopyPixelDataTo(depthData);
            int count = 0;
            for (int i = 0; i < depthData.Length; i++) {
                int depth = depthData[i] >> DepthImageFrame.PlayerIndexBitmaskWidth;
                if (depth >= presenceMinMm && depth <= presenceMaxMm)
                    count++;
            }
            return count;
        } catch {
            return -1;
        } finally {
            if (frame != null) frame.Dispose();
        }
    }

    static void WritePresence(bool present, int pixelCount) {
        try {
            string state = present ? "PRESENT" : "ABSENT";
            string content = string.Format("{0}\n{1}\n{2}",
                state,
                DateTime.UtcNow.ToString("o"),
                pixelCount
            );
            string tmp = PresenceFile + ".tmp";
            File.WriteAllText(tmp, content);
            if (File.Exists(PresenceFile)) File.Delete(PresenceFile);
            File.Move(tmp, PresenceFile);
        } catch {}
    }

    // --- Daemon mode: presence + gesture commands ---
    static void RunDaemon(string snapDir) {
        Log("=== Daemon mode ===");
        LoadPresenceConfig();

        InitSensor(false, true);  // depth only at start
        if (sensor == null) {
            Log("ERROR: no Kinect sensor");
            return;
        }
        Thread.Sleep(1000);
        Log("Depth stream actif — surveillance presence");

        bool wasPresent = false;
        DateTime lastTrigger = DateTime.MinValue;
        DateTime lastConfigCheck = DateTime.Now;
        int configCheckIntervalS = 30;

        while (true) {
            // --- Check for gesture commands ---
            try {
                if (File.Exists(MotorCmdFile)) {
                    string cmd = "";
                    try {
                        cmd = File.ReadAllText(MotorCmdFile).Trim().ToLower();
                        File.Delete(MotorCmdFile);
                    } catch { Thread.Sleep(50); continue; }

                    if (!string.IsNullOrEmpty(cmd)) {
                        Log("CMD: " + cmd);
                        if (cmd == "snap") {
                            Console.WriteLine(Snap(snapDir));
                        } else {
                            RunGesture(cmd);
                        }
                    }
                }
            } catch {}

            // --- Reload config periodically ---
            if ((DateTime.Now - lastConfigCheck).TotalSeconds > configCheckIntervalS) {
                LoadPresenceConfig();
                lastConfigCheck = DateTime.Now;
            }

            // --- Depth scan ---
            int pixels = AnalyzeDepthFrame();
            if (pixels < 0) {
                Thread.Sleep(presenceScanMs);
                continue;
            }

            bool present = pixels >= presencePixelThreshold;

            // State change detection
            if (present && !wasPresent) {
                double sinceLast = (DateTime.Now - lastTrigger).TotalSeconds;
                if (sinceLast >= presenceCooldownS) {
                    Log(string.Format("PRESENCE detected ({0} pixels)", pixels));
                    WritePresence(true, pixels);
                    lastTrigger = DateTime.Now;
                } else {
                    WritePresence(true, pixels);
                }
            } else if (!present && wasPresent) {
                Log(string.Format("ABSENCE ({0} pixels)", pixels));
                WritePresence(false, pixels);
            }

            wasPresent = present;
            Thread.Sleep(presenceScanMs);
        }
    }

    // --- Legacy one-shot mode (backward compatible) ---
    static void RunOneShot(string mode, string snapDir) {
        bool needColor = (mode == "snap");
        InitSensor(needColor, false);
        if (needColor) Thread.Sleep(2000);

        try {
            if (mode == "snap") Console.WriteLine(Snap(snapDir));
            else RunGesture(mode);
        } finally {
            StopSensor();
        }
    }

    static void Main(string[] args) {
        string mode    = args.Length > 0 ? args[0] : "blink";
        string snapDir = args.Length > 1 ? args[1] : @"C:\Users\PC\Pictures";

        dataDir = Environment.GetEnvironmentVariable("CLAUDIUS_DATA_DIR");
        if (string.IsNullOrEmpty(dataDir)) {
            dataDir = Path.GetDirectoryName(System.Reflection.Assembly.GetExecutingAssembly().Location);
            if (string.IsNullOrEmpty(dataDir)) dataDir = ".";
        }

        if (mode == "presence" || mode == "daemon") {
            RunDaemon(snapDir);
        } else {
            RunOneShot(mode, snapDir);
        }
    }
}
