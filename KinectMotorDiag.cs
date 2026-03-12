using System; using System.Runtime.InteropServices; using System.Threading;
class KinectMotorDiag {
    [DllImport("Kinect10.dll")] static extern int NuiInitialize(uint f);
    [DllImport("Kinect10.dll")] static extern void NuiShutdown();
    [DllImport("Kinect10.dll")] static extern int NuiCameraElevationSetAngle(int d);

    static void Main(string[] args) {
        int hr = NuiInitialize(1);
        Console.WriteLine("NuiInitialize: 0x" + hr.ToString("X8"));
        Console.Out.Flush();

        Console.WriteLine("Attente 2s avant SetAngle...");
        Console.Out.Flush();
        Thread.Sleep(2000);

        int hr2 = NuiCameraElevationSetAngle(-15);
        Console.WriteLine("SetAngle(-15): 0x" + hr2.ToString("X8"));
        Console.Out.Flush();
        Thread.Sleep(2000);

        int hr3 = NuiCameraElevationSetAngle(0);
        Console.WriteLine("SetAngle(0): 0x" + hr3.ToString("X8"));
        Console.Out.Flush();

        NuiShutdown();
        Console.WriteLine("done");
    }
}
