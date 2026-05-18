using System;
using System.Runtime.InteropServices;
using System.Text;

namespace Rainmeter
{
    /// <summary>
    /// Rainmeter API shim — provides the Rainmeter API interface for C# plugins.
    /// This is a minimal implementation matching the official RainmeterPluginSDK.
    /// 
    /// In production, replace with the official Rainmeter.API from:
    /// https://github.com/rainmeter/rainmeter-plugin-sdk
    /// </summary>
    public class API
    {
        private IntPtr _rm;

        private API(IntPtr rm)
        {
            _rm = rm;
        }

        public static implicit operator API(IntPtr rm) => new API(rm);

        // --- Reading skin options ---

        public string ReadString(string option, string defaultValue = "", bool replaceVariables = true)
        {
            if (replaceVariables)
            {
                string val = NativeMethods.RmReadString(_rm, option, defaultValue, false);
                return ReplaceVariables(val);
            }
            return NativeMethods.RmReadString(_rm, option, defaultValue, false);
        }

        public int ReadInt(string option, int defaultValue = 0)
        {
            return NativeMethods.RmReadInt(_rm, option, defaultValue);
        }

        public double ReadDouble(string option, double defaultValue = 0.0)
        {
            return NativeMethods.RmReadDouble(_rm, option, defaultValue);
        }

        // --- Skin interaction ---

        public IntPtr GetSkin()
        {
            return NativeMethods.RmGetSkin(_rm);
        }

        public string GetMeasureName()
        {
            return Marshal.PtrToStringUni(NativeMethods.RmGetMeasureName(_rm));
        }

        public void Execute(IntPtr skin, string command)
        {
            NativeMethods.RmExecute(skin, command);
        }

        public void Execute(string command)
        {
            Execute(GetSkin(), command);
        }

        // --- Variable replacement ---

        public string ReplaceVariables(string str)
        {
            IntPtr result = NativeMethods.RmReplaceVariables(_rm, str);
            return Marshal.PtrToStringUni(result) ?? str;
        }

        // --- Logging ---

        public enum LogType
        {
            Error = 1,
            Warning = 2,
            Notice = 3,
            Debug = 4
        }

        public void Log(LogType type, string message)
        {
            NativeMethods.RmLog(_rm, (int)type, message);
        }

        // --- DllExport attribute marker ---
        // Rainmeter's DllExporter.exe looks for this attribute to create unmanaged exports.
        // It's a dummy attribute — the real work happens in the post-build step.
        [AttributeUsage(AttributeTargets.Method)]
        public class DllExportAttribute : Attribute
        {
        }
    }

    /// <summary>
    /// Helper for returning strings from GetString(). 
    /// Manages a pinned string buffer (singleton per measure context).
    /// </summary>
    public static class StringBuffer
    {
        [ThreadStatic]
        private static string _buffer;

        public static IntPtr Update(string value)
        {
            _buffer = value ?? "";
            return Marshal.StringToHGlobalUni(_buffer);
        }
    }

    public static class NativeMethods
    {
        [DllImport("Rainmeter.dll", CharSet = CharSet.Unicode)]
        internal static extern string RmReadString(IntPtr rm, string option, string defaultValue, bool replaceVariables);

        [DllImport("Rainmeter.dll")]
        internal static extern int RmReadInt(IntPtr rm, string option, int defaultValue);

        [DllImport("Rainmeter.dll")]
        internal static extern double RmReadDouble(IntPtr rm, string option, double defaultValue);

        [DllImport("Rainmeter.dll")]
        internal static extern IntPtr RmGetSkin(IntPtr rm);

        [DllImport("Rainmeter.dll", CharSet = CharSet.Unicode)]
        internal static extern IntPtr RmGetMeasureName(IntPtr rm);

        [DllImport("Rainmeter.dll", CharSet = CharSet.Unicode)]
        internal static extern void RmExecute(IntPtr skin, string command);

        [DllImport("Rainmeter.dll", CharSet = CharSet.Unicode)]
        internal static extern IntPtr RmReplaceVariables(IntPtr rm, string str);

        [DllImport("Rainmeter.dll", CharSet = CharSet.Unicode)]
        internal static extern void RmLog(IntPtr rm, int type, string message);
    }
}
