using System;
using System.Runtime.InteropServices;
using Rainmeter;
using RGiesecke.DllExport;

namespace HermesRainmeter
{
    /// <summary>
    /// Rainmeter plugin entry points.
    /// These are the exported C functions that Rainmeter calls.
    /// Marked with [DllExport] from the DllExport NuGet package,
    /// which creates real unmanaged exports in the compiled DLL.
    /// </summary>
    public static class Plugin
    {
        [DllExport]
        public static void Initialize(ref IntPtr data, IntPtr rm)
        {
            Measure measure = new Measure();
            data = GCHandle.ToIntPtr(GCHandle.Alloc(measure));

            API api = (API)rm;
            measure.Initialize(api);
        }

        [DllExport]
        public static void Finalize(IntPtr data)
        {
            Measure measure = data;
            measure.Finalize();

            GCHandle.FromIntPtr(data).Free();
        }

        [DllExport]
        public static void Reload(IntPtr data, IntPtr rm, ref double maxValue)
        {
            Measure measure = data;
            API api = (API)rm;
            measure.Reload(api);
        }

        [DllExport]
        public static double Update(IntPtr data)
        {
            Measure measure = data;
            return measure.Update();
        }

        [DllExport]
        public static IntPtr GetString(IntPtr data)
        {
            Measure measure = data;
            return StringBuffer.Update(measure.GetString());
        }

        [DllExport]
        public static void ExecuteBang(IntPtr data, [MarshalAs(UnmanagedType.LPWStr)] string args)
        {
            Measure measure = data;
            measure.ExecuteBang(args);
        }
    }
}
