import Cocoa
import AuthenticationServices
import CryptoKit

class ViewController: NSViewController, ASWebAuthenticationPresentationContextProviding {
    
    @IBOutlet weak var label_rt: NSTextField!
    @IBOutlet weak var label_at: NSTextField!
    @IBOutlet weak var copyRefreshToken: NSButton!
    @IBOutlet weak var copyAccessToken: NSButton!
    @IBOutlet weak var refreshToken_textview: NSTextField!
    @IBOutlet weak var accessToken_textview: NSTextField!
    
    var codeVerifier: String = ""
    var authSession: ASWebAuthenticationSession? // Authentifizierungssession als Instanzvariable speichern
    
    override func viewDidLoad() {
        super.viewDidLoad()
        copyAccessToken.isHidden = true
        copyRefreshToken.isHidden = true
        refreshToken_textview.isHidden = true
        accessToken_textview.isHidden = true
        label_at.isHidden = true
        label_rt.isHidden = true
    }
    
    @IBAction func IBActionfunccloseApp_senderAnyNSApplicationsharedterminatenilcloseApp(_ sender: Any) {
        NSApplication.shared.terminate(nil)
    }

    @IBAction func StartButton_click(_ sender: Any) {
        startOAuthLogin()
    }
    
    func showMessageBox(title: String) {
        let alert = NSAlert()
        alert.messageText = title
        alert.alertStyle = .warning
        alert.addButton(withTitle: "OK")
        alert.runModal()
    }
    
    func startOAuthLogin() {
        codeVerifier = generateCodeVerifier()
        guard let codeChallenge = generateCodeChallenge(from: codeVerifier) else {
            showMessageBox(title: "Fehler beim Generieren der Code Challenge")
            return
        }

        let authorizationEndpoint = "https://id.mercedes-benz.com/as/authorization.oauth2"
        let clientID = "62778dc4-1de3-44f4-af95-115f06a3a008"
        let redirectURI = "rismycar://login-callback"
        let scope = "email openid profile offline_access phone ciam-uid"
        let responseType = "code"
        let codeChallengeMethod = "S256"
        
        var components = URLComponents(string: authorizationEndpoint)
        components?.queryItems = [
            URLQueryItem(name: "response_type", value: responseType),
            URLQueryItem(name: "client_id", value: clientID),
            URLQueryItem(name: "redirect_uri", value: redirectURI),
            URLQueryItem(name: "scope", value: scope),
            URLQueryItem(name: "code_challenge", value: codeChallenge),
            URLQueryItem(name: "code_challenge_method", value: codeChallengeMethod)
        ]

        guard let authURL = components?.url else {
            showMessageBox(title: "Ungültige URL für OAuth-Login")
            return
        }
        
        authSession = ASWebAuthenticationSession(url: authURL, callbackURLScheme: "rismycar") { [weak self] callbackURL, error in
            guard let self = self else { return }
            if let error = error {
                self.showMessageBox(title: "Fehler bei der Authentifizierung: \(error.localizedDescription)")
                return
            }
            
            guard let callbackURL = callbackURL,
                  let components = URLComponents(url: callbackURL, resolvingAgainstBaseURL: false),
                  let queryItems = components.queryItems,
                  let code = queryItems.first(where: { $0.name == "code" })?.value else {
                self.showMessageBox(title: "Fehler beim Abrufen des Authorization Codes.")
                return
            }
            
            self.exchangeCodeForToken(code: code, redirectURI: redirectURI)
        }
        
        authSession?.presentationContextProvider = self
        authSession?.start()
    }
    
    func exchangeCodeForToken(code: String, redirectURI: String) {
        let tokenEndpoint = "https://id.mercedes-benz.com/as/token.oauth2"
        let clientID = "62778dc4-1de3-44f4-af95-115f06a3a008"
        
        guard let url = URL(string: tokenEndpoint) else {
            showMessageBox(title: "Ungültige Token-URL")
            return
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        
        let bodyParameters = [
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirectURI,
            "client_id": clientID,
            "code_verifier": codeVerifier
        ]
        request.httpBody = bodyParameters.map { "\($0.key)=\($0.value)" }.joined(separator: "&").data(using: .utf8)
        
        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            guard let self = self else { return }
            if let error = error {
                self.showMessageBox(title: "Fehler beim Abrufen des Tokens: \(error.localizedDescription)")
                return
            }
            
            guard let data = data else {
                self.showMessageBox(title: "Keine Daten vom Server erhalten.")
                return
            }
            
            do {
                if let json = try JSONSerialization.jsonObject(with: data, options: []) as? [String: Any],
                   let refreshToken = json["refresh_token"] as? String,
                   let accessToken = json["access_token"] as? String {
                    
                    DispatchQueue.main.async { [weak self] in
                        guard let self = self else { return }
                        self.accessToken_textview.stringValue = accessToken
                        self.refreshToken_textview.stringValue = refreshToken
                        self.refreshToken_textview.isHidden = false
                        self.accessToken_textview.isHidden = false
                        self.copyAccessToken.isHidden = false
                        self.copyRefreshToken.isHidden = false
                        self.label_at.isHidden = false
                        self.label_rt.isHidden = false
                    }
                } else {
                    self.showMessageBox(title: "Fehlende Token-Werte.")
                }
            } catch {
                self.showMessageBox(title: "Fehler beim Verarbeiten der JSON-Daten: \(error.localizedDescription)")
            }
        }.resume()
    }
    
    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        guard let window = self.view.window else {
            fatalError("Window not available")
        }
        return window
    }
    
    func generateCodeVerifier() -> String {
        let characters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~"
        return String((0..<128).map { _ in characters.randomElement()! })
    }
    
    func generateCodeChallenge(from verifier: String) -> String? {
        guard let data = verifier.data(using: .utf8) else { return nil }
        let hashed = SHA256.hash(data: data)
        return Data(hashed).base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }
    @IBAction func copyAccessTokenToClipboard(_ sender: Any) {
         // Hole den Text aus der NSTextView
         let textToCopy = accessToken_textview.stringValue
         
         // Kopiere den Text in die Zwischenablage
         let pasteboard = NSPasteboard.general
         pasteboard.clearContents()
         pasteboard.setString(textToCopy, forType: .string)
         
     }
     
     @IBAction func copyRefreshTokenToClipboard(_ sender: Any) {
         // Hole den Text aus der NSTextView
         let textToCopy = refreshToken_textview.stringValue
         
         // Kopiere den Text in die Zwischenablage
         let pasteboard = NSPasteboard.general
         pasteboard.clearContents()
         pasteboard.setString(textToCopy, forType: .string)
         
     }
}
