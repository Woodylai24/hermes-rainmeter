using System;
using System.Runtime.InteropServices;
using Rainmeter;

namespace HermesRainmeter
{
    /// <summary>
    /// Rainmeter plugin entry points.
    /// These are the exported C functions that Rainmeter calls.
    /// Marked with [DllExport] for Rainmeter's DllExporter.exe post-processor.
    /// </summary>
    public static class Plugin
    {
        [API.DllExport]
        public static void Initialize(ref IntPtr data, IntPtr rm)
        {
            Measure measure = new Measure();
            data = GCHandle.ToIntPtr(GCHandle.Alloc(measure));

            API api = (API)rm;
            measure.Initialize(api);
        }

        [API.DllExport]
        public static void Finalize(IntPtr data)
        {
            Measure measure = data;
            measure.Finalize();

            GCHandle.FromIntPtr(data).Free();
        }

        [API.DllExport]
        public static void Reload(IntPtr data, IntPtr rm, ref double maxValue)
        {
            Measure measure = data;
            API api = (API)rm;
            measure.Reload(api);
        }

        [API.DllExport]
        public static double Update(IntPtr data)
        {
            Measure measure = data;
            return measure.Update();
        }

        [API.DllExport]
        public static IntPtr GetString(IntPtr data)
        {
            Measure measure = data;
            return StringBuffer.Update(measure.GetString());
        }

        [API.DllExport]
        public static void ExecuteBang(IntPtr data, [MarshalAs(UnmanagedType.LPWStr)] string args)
        {
            Measure measure = data;
            measure.ExecuteBang(args);
        }
    }
}
