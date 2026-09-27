#!/usr/bin/env python3
"""
UNIVERSE MEMORY TOOLS
Process memory manipulation, DLL injection, patching

Author: YONDA Agent
Date: 2026-08-23
"""

import os
import sys
import ctypes
from ctypes import wintypes
import struct

# Windows API constants
PROCESS_ALL_ACCESS = 0x1F0FFF
MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
PAGE_EXECUTE_READWRITE = 0x40

# Load Windows APIs
kernel32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi

class MemoryTools:
    """Windows process memory manipulation"""
    
    def __init__(self, pid):
        self.pid = pid
        self.handle = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
        
        if not self.handle:
            raise Exception(f"Failed to open process {pid}")
    
    def __del__(self):
        if hasattr(self, 'handle') and self.handle:
            kernel32.CloseHandle(self.handle)
    
    def read_memory(self, address, size):
        """Read memory from process"""
        buffer = ctypes.create_string_buffer(size)
        bytes_read = ctypes.c_size_t()
        
        success = kernel32.ReadProcessMemory(
            self.handle,
            ctypes.c_void_p(address),
            buffer,
            size,
            ctypes.byref(bytes_read)
        )
        
        if not success:
            return None
        
        return buffer.raw[:bytes_read.value]
    
    def write_memory(self, address, data):
        """Write memory to process"""
        bytes_written = ctypes.c_size_t()
        
        success = kernel32.WriteProcessMemory(
            self.handle,
            ctypes.c_void_p(address),
            data,
            len(data),
            ctypes.byref(bytes_written)
        )
        
        return success and bytes_written.value == len(data)
    
    def search_pattern(self, pattern, start_address=0x10000, end_address=0x7FFFFFFF):
        """Search for byte pattern in memory"""
        results = []
        chunk_size = 4096
        
        current = start_address
        
        while current < end_address:
            data = self.read_memory(current, chunk_size)
            
            if data:
                # Search for pattern
                offset = data.find(pattern)
                if offset != -1:
                    results.append(current + offset)
            
            current += chunk_size
        
        return results
    
    def dump_memory(self, output_path, start_address=0x400000, size=0x100000):
        """Dump process memory to file"""
        data = self.read_memory(start_address, size)
        
        if data:
            with open(output_path, 'wb') as f:
                f.write(data)
            return True
        
        return False
    
    def inject_dll(self, dll_path):
        """Inject DLL into process"""
        dll_path_bytes = dll_path.encode('utf-8') + b'\x00'
        
        # Allocate memory in target process
        alloc_addr = kernel32.VirtualAllocEx(
            self.handle,
            None,
            len(dll_path_bytes),
            MEM_COMMIT | MEM_RESERVE,
            PAGE_EXECUTE_READWRITE
        )
        
        if not alloc_addr:
            return False
        
        # Write DLL path
        if not self.write_memory(alloc_addr, dll_path_bytes):
            return False
        
        # Get LoadLibraryA address
        kernel32_handle = kernel32.GetModuleHandleW("kernel32.dll")
        loadlib_addr = kernel32.GetProcAddress(kernel32_handle, b"LoadLibraryA")
        
        # Create remote thread
        thread_id = wintypes.DWORD()
        thread_handle = kernel32.CreateRemoteThread(
            self.handle,
            None,
            0,
            loadlib_addr,
            alloc_addr,
            0,
            ctypes.byref(thread_id)
        )
        
        if thread_handle:
            kernel32.WaitForSingleObject(thread_handle, 5000)
            kernel32.CloseHandle(thread_handle)
            return True
        
        return False
    
    def list_modules(self):
        """List loaded modules in process"""
        modules = (wintypes.HMODULE * 1024)()
        cb_needed = wintypes.DWORD()
        
        success = psapi.EnumProcessModules(
            self.handle,
            ctypes.byref(modules),
            ctypes.sizeof(modules),
            ctypes.byref(cb_needed)
        )
        
        if not success:
            return []
        
        module_list = []
        count = cb_needed.value // ctypes.sizeof(wintypes.HMODULE)
        
        for i in range(count):
            module_name = ctypes.create_unicode_buffer(260)
            psapi.GetModuleFileNameExW(
                self.handle,
                modules[i],
                module_name,
                ctypes.sizeof(module_name)
            )
            
            if module_name.value:
                module_list.append({
                    'name': os.path.basename(module_name.value),
                    'path': module_name.value,
                    'base': modules[i]
                })
        
        return module_list


def find_process_by_name(process_name):
    """Find process ID by name"""
    import psutil
    
    for proc in psutil.process_iter(['pid', 'name']):
        if process_name.lower() in proc.info['name'].lower():
            return proc.info['pid']
    
    return None


# Cheat Engine-like value scanner
class ValueScanner:
    """Scan and modify values in memory"""
    
    def __init__(self, pid):
        self.mem = MemoryTools(pid)
        self.addresses = []
    
    def first_scan(self, value, value_type='int32'):
        """Initial scan for value"""
        print(f"🔍 Scanning for {value} ({value_type})...")
        
        # Convert value to bytes
        if value_type == 'int32':
            pattern = struct.pack('<i', value)
        elif value_type == 'float':
            pattern = struct.pack('<f', value)
        elif value_type == 'int64':
            pattern = struct.pack('<q', value)
        else:
            pattern = value.encode()
        
        # Search memory
        self.addresses = self.mem.search_pattern(pattern)
        
        print(f"✅ Found {len(self.addresses)} addresses")
        return self.addresses
    
    def next_scan(self, value, value_type='int32'):
        """Rescan previous addresses"""
        print(f"🔍 Rescanning for {value}...")
        
        if value_type == 'int32':
            pattern = struct.pack('<i', value)
        elif value_type == 'float':
            pattern = struct.pack('<f', value)
        else:
            pattern = value.encode()
        
        # Filter addresses
        valid_addresses = []
        for addr in self.addresses:
            data = self.mem.read_memory(addr, len(pattern))
            if data == pattern:
                valid_addresses.append(addr)
        
        self.addresses = valid_addresses
        print(f"✅ {len(self.addresses)} addresses remaining")
        return self.addresses
    
    def write_value(self, value, value_type='int32'):
        """Write value to all found addresses"""
        if value_type == 'int32':
            data = struct.pack('<i', value)
        elif value_type == 'float':
            data = struct.pack('<f', value)
        else:
            data = value.encode()
        
        success_count = 0
        for addr in self.addresses:
            if self.mem.write_memory(addr, data):
                success_count += 1
        
        print(f"✅ Wrote to {success_count}/{len(self.addresses)} addresses")
        return success_count


if __name__ == "__main__":
    print("🔥 UNIVERSE MEMORY TOOLS")
    print("\nUsage examples:")
    print("  mem = MemoryTools(pid)")
    print("  mem.dump_memory('dump.bin', 0x400000, 0x100000)")
    print("  mem.inject_dll('C:/path/to/mod.dll')")
    print("\n  scanner = ValueScanner(pid)")
    print("  scanner.first_scan(100, 'int32')")
    print("  scanner.next_scan(200, 'int32')")
    print("  scanner.write_value(9999, 'int32')")
