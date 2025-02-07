using System.Reflection;
using Microsoft.Win32;
using System.Runtime;

namespace mbtokenrequester
{
    [System.Runtime.Versioning.SupportedOSPlatform("windows")]
    class RegistryConfig
    {
        public RegistryConfig(string uriScheme)
        {
            CustomUriScheme = uriScheme;
        }

        public void Configure()
        {
            if (NeedToAddKeys()) AddRegKeys();
        }

        public void DeleteRegKeys()
        {
            using (var classesKey = Registry.CurrentUser.OpenSubKey(RootKeyPath, true))
            {
                if (classesKey?.OpenSubKey(CustomUriScheme) != null)
                {
                    classesKey.DeleteSubKeyTree(CustomUriScheme, false);
                }
            }
        }

        private string CustomUriScheme { get; }

        string CustomUriSchemeKeyPath => RootKeyPath + @"\" + CustomUriScheme;
        string CustomUriSchemeKeyValueValue => "URL:" + CustomUriScheme;
        string CommandKeyPath => CustomUriSchemeKeyPath + @"\shell\open\command";

        const string RootKeyPath = @"Software\Classes";

        const string CustomUriSchemeKeyValueName = "";
        const string ShellKeyName = "shell";
        const string OpenKeyName = "open";
        const string CommandKeyName = "command";
        const string CommandKeyValueName = "";
        const string CommandKeyValueFormat = "\"{0}\\callback.bat\" \"%1\"";
        static string CommandKeyValueValue => string.Format(CommandKeyValueFormat, Path.GetDirectoryName(System.AppContext.BaseDirectory));

        const string UrlProtocolValueName = "URL Protocol";
        const string UrlProtocolValueValue = "";

        bool NeedToAddKeys()
        {
            var addKeys = false;

            using (var commandKey = Registry.CurrentUser.OpenSubKey(CommandKeyPath))
            {
                var commandValue = commandKey?.GetValue(CommandKeyValueName);
                addKeys |= !CommandKeyValueValue.Equals(commandValue);
            }

            using (var customUriSchemeKey = Registry.CurrentUser.OpenSubKey(CustomUriSchemeKeyPath))
            {
                var uriValue = customUriSchemeKey?.GetValue(CustomUriSchemeKeyValueName);
                var protocolValue = customUriSchemeKey?.GetValue(UrlProtocolValueName);
                addKeys |= !CustomUriSchemeKeyValueValue.Equals(uriValue);
                addKeys |= !UrlProtocolValueValue.Equals(protocolValue);
            }

            return addKeys;
        }

        void AddRegKeys()
        {
            using (var classesKey = Registry.CurrentUser.OpenSubKey(RootKeyPath, true))
            {
                using (var root = classesKey!.OpenSubKey(CustomUriScheme, true) ??
                    classesKey.CreateSubKey(CustomUriScheme, true))
                {
                    root.SetValue(CustomUriSchemeKeyValueName, CustomUriSchemeKeyValueValue);
                    root.SetValue(UrlProtocolValueName, UrlProtocolValueValue);

                    using (var shell = root.OpenSubKey(ShellKeyName, true) ??
                            root.CreateSubKey(ShellKeyName, true))
                    {
                        using (var open = shell.OpenSubKey(OpenKeyName, true) ??
                                shell.CreateSubKey(OpenKeyName, true))
                        {
                            using (var command = open.OpenSubKey(CommandKeyName, true) ??
                                    open.CreateSubKey(CommandKeyName, true))
                            {
                                command.SetValue(CommandKeyValueName, CommandKeyValueValue);
                            }
                        }
                    }
                }
            }
        }
    }
}
