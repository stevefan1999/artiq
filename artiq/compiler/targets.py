import os, sys, tempfile, subprocess, io
from artiq.compiler import types, ir
from llvmlite_artiq import ir as ll, binding as llvm

llvm.initialize()
llvm.initialize_all_targets()
llvm.initialize_all_asmprinters()

class RunTool:
    def __init__(self, pattern, **tempdata):
        self._pattern   = pattern
        self._tempdata  = tempdata
        self._tempnames = {}
        self._tempfiles = {}

    def __enter__(self):
        for key, data in self._tempdata.items():
            if data is None:
                fd, filename = tempfile.mkstemp()
                os.close(fd)
                self._tempnames[key] = filename
            else:
                with tempfile.NamedTemporaryFile(delete=False) as f:
                    f.write(data)
                    self._tempnames[key] = f.name

        cmdline = []
        for argument in self._pattern:
            cmdline.append(argument.format(**self._tempnames))

        process = subprocess.Popen(cmdline, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   universal_newlines=True)
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            raise Exception("{} invocation failed: {}".
                            format(cmdline[0], stderr))

        self._tempfiles["__stdout__"] = io.StringIO(stdout)
        for key in self._tempdata:
            if self._tempdata[key] is None:
                self._tempfiles[key] = open(self._tempnames[key], "rb")
        return self._tempfiles

    def __exit__(self, exc_typ, exc_value, exc_trace):
        for file in self._tempfiles.values():
            file.close()
        for filename in self._tempnames.values():
            os.unlink(filename)

def _dump(target, kind, suffix, content):
    if target is not None:
        print("====== {} DUMP ======".format(kind.upper()), file=sys.stderr)
        content_value = content()
        if isinstance(content_value, str):
            content_value = bytes(content_value, 'utf-8')
        if target == "":
            file = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        else:
            file = open(target + suffix, "wb")
        file.write(content_value)
        file.close()
        print("{} dumped as {}".format(kind, file.name), file=sys.stderr)

class Target:
    """
    A description of the target environment where the binaries
    generated by the ARTIQ compiler will be deployed.

    :var triple: (string)
        LLVM target triple, e.g. ``"or1k"``
    :var data_layout: (string)
        LLVM target data layout, e.g. ``"E-m:e-p:32:32-i64:32-f64:32-v64:32-v128:32-a:0:32-n32"``
    :var features: (list of string)
        LLVM target CPU features, e.g. ``["mul", "div", "ffl1"]``
    :var print_function: (string)
        Name of a formatted print functions (with the signature of ``printf``)
        provided by the target, e.g. ``"printf"``.
    :var little_endian: (boolean)
        Whether the code will be executed on a little-endian machine. This cannot be always
        determined from data_layout due to JIT.
    :var now_pinning: (boolean)
        Whether the target implements the now-pinning RTIO optimization.
    """
    triple = "unknown"
    data_layout = ""
    features = []
    print_function = "printf"
    little_endian = False
    now_pinning = True

    tool_ld = "ld.lld"
    tool_strip = "llvm-strip"
    tool_addr2line = "llvm-addr2line"
    tool_cxxfilt = "llvm-cxxfilt"

    def __init__(self):
        self.llcontext = ll.Context()

    def target_machine(self):
        lltarget = llvm.Target.from_triple(self.triple)
        llmachine = lltarget.create_target_machine(
                        features=",".join(["+{}".format(f) for f in self.features]),
                        reloc="pic", codemodel="default")
        llmachine.set_asm_verbosity(True)
        return llmachine

    def optimize(self, llmodule):
        llpassmgr = llvm.create_module_pass_manager()

        # Register our alias analysis passes.
        llpassmgr.add_basic_alias_analysis_pass()
        llpassmgr.add_type_based_alias_analysis_pass()

        # Start by cleaning up after our codegen and exposing as much
        # information to LLVM as possible.
        llpassmgr.add_constant_merge_pass()
        llpassmgr.add_cfg_simplification_pass()
        llpassmgr.add_instruction_combining_pass()
        llpassmgr.add_sroa_pass()
        llpassmgr.add_dead_code_elimination_pass()
        llpassmgr.add_function_attrs_pass()
        llpassmgr.add_global_optimizer_pass()

        # Now, actually optimize the code.
        llpassmgr.add_function_inlining_pass(275)
        llpassmgr.add_ipsccp_pass()
        llpassmgr.add_instruction_combining_pass()
        llpassmgr.add_gvn_pass()
        llpassmgr.add_cfg_simplification_pass()
        llpassmgr.add_licm_pass()

        # Clean up after optimizing.
        llpassmgr.add_dead_arg_elimination_pass()
        llpassmgr.add_global_dce_pass()

        llpassmgr.run(llmodule)

    def compile(self, module):
        """Compile the module to a relocatable object for this target."""

        if os.getenv("ARTIQ_DUMP_SIG"):
            print("====== MODULE_SIGNATURE DUMP ======", file=sys.stderr)
            print(module, file=sys.stderr)

        if os.getenv("ARTIQ_IR_NO_LOC") is not None:
            ir.BasicBlock._dump_loc = False

        type_printer = types.TypePrinter()
        _dump(os.getenv("ARTIQ_DUMP_IR"), "ARTIQ IR", ".txt",
              lambda: "\n".join(fn.as_entity(type_printer) for fn in module.artiq_ir))

        llmod = module.build_llvm_ir(self)

        try:
            llparsedmod = llvm.parse_assembly(str(llmod))
            llparsedmod.verify()
        except RuntimeError:
            _dump("", "LLVM IR (broken)", ".ll", lambda: str(llmod))
            raise

        _dump(os.getenv("ARTIQ_DUMP_UNOPT_LLVM"), "LLVM IR (generated)", "_unopt.ll",
              lambda: str(llparsedmod))

        self.optimize(llparsedmod)

        _dump(os.getenv("ARTIQ_DUMP_LLVM"), "LLVM IR (optimized)", ".ll",
              lambda: str(llparsedmod))

        return llparsedmod

    def assemble(self, llmodule):
        llmachine = self.target_machine()

        _dump(os.getenv("ARTIQ_DUMP_ASM"), "Assembly", ".s",
              lambda: llmachine.emit_assembly(llmodule))

        _dump(os.getenv("ARTIQ_DUMP_OBJ"), "Object file", ".o",
              lambda: llmachine.emit_object(llmodule))

        return llmachine.emit_object(llmodule)

    def link(self, objects):
        """Link the relocatable objects into a shared library for this target."""
        with RunTool([self.tool_ld, "-shared", "--eh-frame-hdr"] +
                     ["{{obj{}}}".format(index) for index in range(len(objects))] +
                     ["-o", "{output}"],
                     output=None,
                     **{"obj{}".format(index): obj for index, obj in enumerate(objects)}) \
                as results:
            library = results["output"].read()

            _dump(os.getenv("ARTIQ_DUMP_ELF"), "Shared library", ".elf",
                  lambda: library)

            return library

    def compile_and_link(self, modules):
        return self.link([self.assemble(self.compile(module)) for module in modules])

    def strip(self, library):
        with RunTool([self.tool_strip, "--strip-debug", "{library}", "-o", "{output}"],
                     library=library, output=None) \
                as results:
            return results["output"].read()

    def symbolize(self, library, addresses):
        if addresses == []:
            return []

        # We got a list of return addresses, i.e. addresses of instructions
        # just after the call. Offset them back to get an address somewhere
        # inside the call instruction (or its delay slot), since that's what
        # the backtrace entry should point at.
        offset_addresses = [hex(addr - 1) for addr in addresses]
        with RunTool([self.tool_addr2line, "--addresses",  "--functions", "--inlines",
                      "--demangle", "--exe={library}"] + offset_addresses,
                     library=library) \
                as results:
            lines = iter(results["__stdout__"].read().rstrip().split("\n"))
            backtrace = []
            while True:
                try:
                    address_or_function = next(lines)
                except StopIteration:
                    break
                if address_or_function[:2] == "0x":
                    address  = int(address_or_function[2:], 16) + 1 # remove offset
                    function = next(lines)
                else:
                    address  = backtrace[-1][4] # inlined
                    function = address_or_function
                location = next(lines)

                filename, line = location.rsplit(":", 1)
                if filename == "??" or filename == "<synthesized>":
                    continue
                if line == "?":
                    line = -1
                else:
                    line = int(line)
                # can't get column out of addr2line D:
                backtrace.append((filename, line, -1, function, address))
            return backtrace

    def demangle(self, names):
        with RunTool([self.tool_cxxfilt] + names) as results:
            return results["__stdout__"].read().rstrip().split("\n")

class NativeTarget(Target):
    def __init__(self):
        super().__init__()
        self.triple = llvm.get_default_triple()
        host_data_layout = str(llvm.targets.Target.from_default_triple().create_target_machine().target_data)
        assert host_data_layout[0] in "eE"
        self.little_endian = host_data_layout[0] == "e"

class OR1KTarget(Target):
    triple = "or1k-linux"
    data_layout = "E-m:e-p:32:32-i8:8:8-i16:16:16-i64:32:32-" \
                  "f64:32:32-v64:32:32-v128:32:32-a0:0:32-n32"
    features = ["mul", "div", "ffl1", "cmov", "addc"]
    print_function = "core_log"
    little_endian = False
    now_pinning = True

    tool_ld = "or1k-linux-ld"
    tool_strip = "or1k-linux-strip"
    tool_addr2line = "or1k-linux-addr2line"
    tool_cxxfilt = "or1k-linux-c++filt"

class CortexA9Target(Target):
    triple = "armv7-unknown-linux-gnueabihf"
    data_layout = "e-m:e-p:32:32-i64:64-v128:64:128-a:0:32-n32-S64"
    features = ["dsp", "fp16", "neon", "vfp3"]
    print_function = "core_log"
    little_endian = True
    now_pinning = False

    tool_ld = "armv7-unknown-linux-gnueabihf-ld"
    tool_strip = "armv7-unknown-linux-gnueabihf-strip"
    tool_addr2line = "armv7-unknown-linux-gnueabihf-addr2line"
    tool_cxxfilt = "armv7-unknown-linux-gnueabihf-c++filt"
