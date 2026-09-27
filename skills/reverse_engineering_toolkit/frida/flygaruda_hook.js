
// FlyGaruda Miles & Tier Hook
// by YONDA Agent - 2026-08-24

console.log("[*] FlyGaruda Hook Loading...");

// Hook Flutter native functions
Java.perform(function() {
    console.log("[*] Java.perform started");
    
    // Try to find SharedPreferences
    var SharedPreferences = Java.use("android.content.SharedPreferences");
    var Editor = Java.use("android.content.SharedPreferences$Editor");
    
    // Hook getInt (for miles value)
    SharedPreferences.getInt.overload('java.lang.String', 'int').implementation = function(key, defValue) {
        var result = this.getInt(key, defValue);
        
        if (key.toLowerCase().includes("mile")) {
            console.log("[MILES] Original: " + result + " → Patched: 450600");
            return 450600;
        }
        
        return result;
    };
    
    // Hook getLong (for miles as long)
    SharedPreferences.getLong.overload('java.lang.String', 'long').implementation = function(key, defValue) {
        var result = this.getLong(key, defValue);
        
        if (key.toLowerCase().includes("mile")) {
            console.log("[MILES LONG] Original: " + result + " → Patched: 450600");
            return 450600;
        }
        
        return result;
    };
    
    // Hook getString (for tier/card)
    SharedPreferences.getString.overload('java.lang.String', 'java.lang.String').implementation = function(key, defValue) {
        var result = this.getString(key, defValue);
        
        if (key.toLowerCase().includes("tier") || key.toLowerCase().includes("card")) {
            console.log("[TIER/CARD] Key: " + key + ", Original: " + result + " → Patched: PLATINUM");
            return "PLATINUM";
        }
        
        if (result && (result.toLowerCase() === "blue" || result.toLowerCase() === "silver")) {
            console.log("[CARD COLOR] Changing " + result + " → PLATINUM");
            return "PLATINUM";
        }
        
        return result;
    };
    
    console.log("[✓] SharedPreferences hooks installed!");
});

// Hook native libapp.so functions
Interceptor.attach(Module.findExportByName("libapp.so", null), {
    onEnter: function(args) {
        // This will hook all libapp.so calls
    }
});

console.log("[✓] FlyGaruda Hook Ready!");
console.log("[→] Miles will always return: 450,600");
console.log("[→] Tier will always return: PLATINUM");
