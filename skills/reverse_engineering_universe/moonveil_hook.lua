-- MOONVEIL RUNTIME DEOBFUSCATION HOOK
-- Load this BEFORE the obfuscated script to capture decrypted code

local original_load = load
local original_loadstring = loadstring
local captured_code = {}

-- Hook load/loadstring to capture deobfuscated bytecode
function load(chunk, ...)
    if type(chunk) == "string" and #chunk > 100 then
        table.insert(captured_code, chunk)
        print("[HOOK] Captured code chunk: " .. #chunk .. " bytes")
    end
    return original_load(chunk, ...)
end

loadstring = load

-- Load the obfuscated script
dofile("cdid_obfuscated.lua")

-- Save captured code
local f = io.open("cdid_captured.lua", "w")
for i, code in ipairs(captured_code) do
    f:write("-- CHUNK " .. i .. "\n")
    f:write(code)
    f:write("\n\n")
end
f:close()

print("[HOOK] Saved " .. #captured_code .. " code chunks to cdid_captured.lua")
