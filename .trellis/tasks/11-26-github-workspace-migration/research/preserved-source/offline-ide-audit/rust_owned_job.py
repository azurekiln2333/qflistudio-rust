# Copied narrow OwnedJob helper from Note; source SHA256 bde7ff5454b22b6c43d8eab22abb2503590cb2ffe08cc55be7d0cf4bc7e32e54
import ctypes as C
from ctypes import wintypes as W
import os
import subprocess

class Limits(C.Structure):
    _fields_ = [("processTime", C.c_longlong), ("jobTime", C.c_longlong), ("flags", W.DWORD),
                ("minWs", C.c_size_t), ("maxWs", C.c_size_t), ("activeLimit", W.DWORD),
                ("affinity", C.c_size_t), ("priority", W.DWORD), ("scheduling", W.DWORD)]


class ExtendedLimits(C.Structure):
    _fields_ = [("basic", Limits), ("io", C.c_ulonglong * 6),
                ("processMemory", C.c_size_t), ("jobMemory", C.c_size_t),
                ("peakProcess", C.c_size_t), ("peakJob", C.c_size_t)]


class Accounting(C.Structure):
    _fields_ = [("times", C.c_longlong * 4), ("faults", W.DWORD),
                ("total", W.DWORD), ("active", W.DWORD), ("terminated", W.DWORD)]


class OwnedJob:
    """Assign while suspended: every descendant stays in this private job."""
    def __init__(self):
        self.k = C.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreateJobObjectW": ([C.c_void_p, W.LPCWSTR], W.HANDLE),
            "SetInformationJobObject": ([W.HANDLE, C.c_int, C.c_void_p, W.DWORD], W.BOOL),
            "QueryInformationJobObject": ([W.HANDLE, C.c_int, C.c_void_p, W.DWORD, C.c_void_p], W.BOOL),
            "AssignProcessToJobObject": ([W.HANDLE, W.HANDLE], W.BOOL),
            "TerminateJobObject": ([W.HANDLE, W.UINT], W.BOOL),
            "TerminateProcess": ([W.HANDLE, W.UINT], W.BOOL),
            "ResumeThread": ([W.HANDLE], W.DWORD), "CloseHandle": ([W.HANDLE], W.BOOL),
            "WaitForSingleObject": ([W.HANDLE, W.DWORD], W.DWORD),
            "GetExitCodeProcess": ([W.HANDLE, C.POINTER(W.DWORD)], W.BOOL),
            "GetProcessId": ([W.HANDLE], W.DWORD),
            "GetProcessTimes": ([W.HANDLE] + [C.POINTER(W.FILETIME)] * 4, W.BOOL),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.k, name)
            function.argtypes, function.restype = args, result
        self.job, self.process, self.record = self.k.CreateJobObjectW(None, None), None, {}
        if not self.job:
            raise C.WinError(C.get_last_error())
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway.
        self.check(self.k.SetInformationJobObject(self.job, 9, C.byref(limits), C.sizeof(limits)))

    @staticmethod
    def check(value):
        if not value:
            raise C.WinError(C.get_last_error())

    def start(self, command, directory, env, stdout, stderr):
        import _winapi
        import msvcrt
        with open(os.devnull, "rb") as null:
            handles = [msvcrt.get_osfhandle(f.fileno()) for f in (null, stdout, stderr)]
            previous = [os.get_handle_inheritable(h) for h in handles]
            try:
                for handle in handles:
                    os.set_handle_inheritable(handle, True)
                startup = subprocess.STARTUPINFO()
                startup.dwFlags = subprocess.STARTF_USESTDHANDLES
                startup.hStdInput, startup.hStdOutput, startup.hStdError = handles
                startup.lpAttributeList = {"handle_list": list(dict.fromkeys(handles))}
                hp, ht, pid, tid = _winapi.CreateProcess(None, subprocess.list2cmdline(command),
                    None, None, True, 0x4 | 0x08000000, env, str(directory), startup)
                self.process = hp
                self.record = {"pid": pid, "threadId": tid, "createdSuspended": True,
                               "assignedBeforeResume": False, "terminal": False}
                try:
                    stamps = [W.FILETIME() for _ in range(4)]
                    self.check(self.k.GetProcessTimes(hp, *(C.byref(s) for s in stamps)))
                    self.record["creationFiletime100ns"] = str((stamps[0].dwHighDateTime << 32) | stamps[0].dwLowDateTime)
                    if self.k.GetProcessId(hp) != pid:
                        raise RuntimeError("Exact owned process handle identity mismatch")
                    self.check(self.k.AssignProcessToJobObject(self.job, hp))
                    self.record["assignedBeforeResume"] = True
                    if self.k.ResumeThread(ht) != 1:
                        raise RuntimeError("Suspended root did not resume from its single suspension")
                finally:
                    self.k.CloseHandle(ht)
            finally:
                for handle, inherit in zip(handles, previous):
                    os.set_handle_inheritable(handle, inherit)

    def empty(self):
        info = Accounting()
        self.check(self.k.QueryInformationJobObject(self.job, 1, C.byref(info), C.sizeof(info), None))
        self.record["jobActiveProcesses"] = int(info.active)
        terminal = self.process is None or self.k.WaitForSingleObject(self.process, 0) == 0
        self.record["terminal"] = terminal
        if terminal and self.process:
            code = W.DWORD()
            self.check(self.k.GetExitCodeProcess(self.process, C.byref(code)))
            self.record["exitCode"] = int(code.value)
        return terminal and info.active == 0

    def stop(self):
        self.check(self.k.TerminateJobObject(self.job, 124))
        if self.process and not self.record.get("assignedBeforeResume"):
            self.check(self.k.TerminateProcess(self.process, 124))  # Own never-resumed root only.

    def close(self):
        if self.process:
            self.k.CloseHandle(self.process)
        self.k.CloseHandle(self.job)

