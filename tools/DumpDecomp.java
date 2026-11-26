// Dump decompiled C for functions whose names match any filter substring.
//
// 用法（Ghidra headless）:
//   analyzeHeadless <proj_dir> <proj_name> \
//     -import target.ko \
//     -scriptPath <本目录> \
//     -postScript DumpDecomp.java <输出文件> [过滤1,过滤2,...] \
//     -overwrite
//
// 例:
//   analyzeHeadless /tmp/ghproj swproj -import switch.ko \
//     -scriptPath ~/ghscripts \
//     -postScript DumpDecomp.java out.c FloodControl,Carrier,Alarm,init_switch
//
// 不带过滤参数则导出全部函数。

import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import java.nio.file.*;

public class DumpDecomp extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 1) {
            println("用法: DumpDecomp.java <输出文件> [过滤子串,...]");
            return;
        }
        String out = args[0];
        String[] filters = args.length > 1 ? args[1].split(",") : new String[0];

        DecompInterface di = new DecompInterface();
        di.setOptions(new DecompileOptions());
        di.openProgram(currentProgram);

        StringBuilder sb = new StringBuilder();
        FunctionManager fm = currentProgram.getFunctionManager();
        int done = 0, failed = 0;

        for (Function f : fm.getFunctions(true)) {
            String n = f.getName();
            if (filters.length > 0) {
                boolean hit = false;
                for (String p : filters) {
                    if (n.contains(p)) { hit = true; break; }
                }
                if (!hit) continue;
            }
            DecompileResults r = di.decompileFunction(f, 90, monitor);
            sb.append("/* ===== ").append(n)
              .append(" @ ").append(f.getEntryPoint()).append(" ===== */\n");
            if (r != null && r.decompileCompleted()) {
                sb.append(r.getDecompiledFunction().getC()).append("\n\n");
                done++;
            } else {
                sb.append("/* DECOMPILE FAILED */\n\n");
                failed++;
            }
        }

        Files.write(Paths.get(out), sb.toString().getBytes("UTF-8"));
        println("wrote " + out + "  ok=" + done + " failed=" + failed);
    }
}
