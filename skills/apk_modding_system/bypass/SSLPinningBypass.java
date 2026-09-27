package com.vvvip.bypass;

import javax.net.ssl.*;
import java.security.cert.X509Certificate;
import java.security.SecureRandom;

/**
 * SSL Pinning Bypass for MITM attacks
 * Works on PUBGM, MLBB, Free Fire, etc
 */
public class SSLPinningBypass {
    
    public static void disableSSLPinning() {
        try {
            // Trust all certificates
            TrustManager[] trustAllCerts = new TrustManager[]{
                new X509TrustManager() {
                    public X509Certificate[] getAcceptedIssuers() {
                        return new X509Certificate[0];
                    }
                    
                    public void checkClientTrusted(X509Certificate[] certs, String authType) {
                        // Trust all clients
                    }
                    
                    public void checkServerTrusted(X509Certificate[] certs, String authType) {
                        // Trust all servers
                    }
                }
            };
            
            // Install the all-trusting trust manager
            SSLContext sc = SSLContext.getInstance("TLS");
            sc.init(null, trustAllCerts, new SecureRandom());
            HttpsURLConnection.setDefaultSSLSocketFactory(sc.getSocketFactory());
            
            // Install the all-trusting host verifier
            HttpsURLConnection.setDefaultHostnameVerifier(new HostnameVerifier() {
                public boolean verify(String hostname, SSLSession session) {
                    return true;
                }
            });
            
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
    
    // Call this from MainActivity onCreate
    public static void init() {
        disableSSLPinning();
    }
}
