using IdentityModel.Client;
using IdentityModel.OidcClient;
using System.Diagnostics;
using System.Runtime.InteropServices;
using Serilog;
using Microsoft.Extensions.Configuration;

namespace mbtokenrequester
{
    class Program
    {
        private static IConfiguration Configuration;

        static async Task Main(string[] args)
        {
            try
            {

                Configuration = new ConfigurationBuilder()
                    .AddJsonFile("appsettings.json")
                    .Build();

                Log.Logger = new LoggerConfiguration()
                    .Enrich.FromLogContext()
                    .ReadFrom.Configuration(Configuration)
                    .CreateLogger();


                if (args.Any())
                {

                    Log.Information($"Args {args[0]}");
                    await ProcessCallback(args[0]);
                }
                else
                {
                    await Run();
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine(ex.Message);
                Console.ReadLine();

                //Log.Fatal(ex, "Host terminated unexpectedly");
            }
            finally
            {
                await Log.CloseAndFlushAsync();
            }

            //Console.ReadLine();
        }

        private static async Task ProcessCallback(string args)
        {
            Log.Information($"Args: {args}");
            var response = new AuthorizeResponse(args);
            if (!String.IsNullOrWhiteSpace(response.State))
            {
                Console.WriteLine($"Found state: {response.State}");
                var callbackManager = new CallbackManager(response.State);
                await callbackManager.RunClient(args);
            }
            else
            {
                Console.WriteLine("Error: no state on response");
            }
        }



        static async Task Run()
        {
            var CustomUriScheme = Configuration["AppSettings:CustomUriScheme"];


            if (OperatingSystem.IsWindows())
            {
                new RegistryConfig(CustomUriScheme).Configure();
            }

            Log.Information("+-----------------------+");
            Log.Information("|  Sign in with OIDC    |");
            Log.Information("+-----------------------+");
            Log.Information("");
            if (!OperatingSystem.IsMacOS())
            {
                Log.Information("Press any key to sign in...");
                Console.ReadKey();
            }

            Program p = new Program();
            await p.SignIn();

            if (OperatingSystem.IsWindows())
            {
                new RegistryConfig(CustomUriScheme).DeleteRegKeys();
            }

        }

        private async Task SignIn()
        {
            // create a redirect URI using the custom redirect uri rismycar://login-callback
            var CustomUriScheme = Configuration["AppSettings:CustomUriScheme"];
            string redirectUri = string.Format(CustomUriScheme + Configuration["AppSettings:uri-callback"]);
            Log.Information("redirect URI: " + redirectUri);

            // HttpClientHandler handler = new HttpClientHandler();
            // handler.ServerCertificateCustomValidationCallback = HttpClientHandler.DangerousAcceptAnyServerCertificateValidator;

            var options = new OidcClientOptions
            {
                Authority = Configuration["AppSettings:Authority"],
                ClientId = Configuration["AppSettings:ClientId"],
                Scope = Configuration["AppSettings:Scope"],
                RedirectUri = redirectUri,
                DisablePushedAuthorization = true,
                // BackchannelHandler = handler,
            };

            Log.Information(options.ToString());

            var client = new OidcClient(options);
            var state = await client.PrepareLoginAsync();

            Log.Information($"Start URL: {state.StartUrl}");

            var callbackManager = new CallbackManager(state.State);


            // open system browser to start authentication
            Process.Start(new ProcessStartInfo
            {
                FileName = state.StartUrl,
                UseShellExecute = true
            });

            Log.Information("Running callback manager");
            var response = await callbackManager.RunServer();

            Log.Information($"Response from authorize endpoint: {response}");

            // Brings the Console to Focus.
            if (OperatingSystem.IsWindows())
            {
                BringConsoleToFront();
            }

            var result = await client.ProcessResponseAsync(response, state);

            if (OperatingSystem.IsWindows())
            {
                BringConsoleToFront();
            }

            if (result.IsError)
            {
                Log.Error("\n\nError:\n{0}", result.Error);
            }
            else
            {
                Log.Information("\n\nClaims:");
                foreach (var claim in result.User.Claims)
                {
                    Log.Information("{0}: {1}", claim.Type, claim.Value);
                }

                Console.WriteLine();
                Log.Information("Access token:\n{0}", result.AccessToken);
                Console.WriteLine();

                if (!string.IsNullOrWhiteSpace(result.RefreshToken))
                {
                    Log.Information("Refresh token:\n{0}", result.RefreshToken);
                }

                Console.WriteLine();
                Console.WriteLine("Press any key to close the app...");
                Console.ReadLine();
            }
        }

        // Hack to bring the Console window to front.
        // ref: http://stackoverflow.com/a/12066376
        [DllImport("kernel32.dll", ExactSpelling = true)]
        [System.Runtime.Versioning.SupportedOSPlatform("windows")]
        public static extern IntPtr GetConsoleWindow();

        [DllImport("user32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        [System.Runtime.Versioning.SupportedOSPlatform("windows")]
        public static extern bool SetForegroundWindow(IntPtr hWnd);

        [System.Runtime.Versioning.SupportedOSPlatform("windows")]
        public void BringConsoleToFront()
        {
            SetForegroundWindow(GetConsoleWindow());
        }
    }
}