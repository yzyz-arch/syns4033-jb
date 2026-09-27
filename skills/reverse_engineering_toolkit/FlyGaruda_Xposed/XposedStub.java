package de.robv.android.xposed;

public interface IXposedHookLoadPackage {
    void handleLoadPackage(XC_LoadPackage.LoadPackageParam lpparam) throws Throwable;
}

class XposedBridge {
    public static void log(String text) {}
}

class XposedHelpers {
    public static Object findAndHookMethod(Class<?> clazz, String methodName, Object... parameterTypesAndCallback) {
        return null;
    }
}

class XC_MethodHook {
    public static class MethodHookParam {
        public Object[] args;
        public Object getResult() { return null; }
        public void setResult(Object result) {}
    }
    
    protected void afterHookedMethod(MethodHookParam param) throws Throwable {}
}

class XC_LoadPackage {
    public static class LoadPackageParam {
        public String packageName;
    }
}

class XSharedPreferences {}
