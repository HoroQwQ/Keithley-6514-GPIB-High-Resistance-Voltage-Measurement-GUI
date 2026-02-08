clc; clear; close all;

%% ===== 配置 =====
resource   = "GPIB0::14::INSTR";  % 按 visadevlist 改成你的
T_total_s  = 150;                 % 总采集时长
chunkN     = 1;                   % 1=真正实时；>1=每次READ?取一批更快
nplc       = 0.01;                
saveEveryN = 200;                

%% ===== 连接 =====
d = visadev(resource);
configureTerminator(d,"LF");     
d.Timeout = 10;
cleanupObj = onCleanup(@() cleanup6514(d));

idn = writeread(d,"*IDN?");
disp("Connected: " + strtrim(idn));

%% ===== 初始化 =====
writeline(d,"*RST");
writeline(d,"*CLS");


writeline(d,"FUNC 'VOLT'");
writeline(d,"VOLT:RANG:AUTO ON");

% ---- 零点校正----
% SYST:ZCOR:ACQ 只能在 ZCH ON 时执行；否则会报错（手册有NOTE）:contentReference[oaicite:7]{index=7}
writeline(d,"SYST:ZCH ON");
writeline(d,"INIT");
writeline(d,"SYST:ZCOR:ACQ");
writeline(d,"SYST:ZCH OFF");
writeline(d,"SYST:ZCOR ON");

% ---- 高速采样常用设置 ----
writeline(d,"SYST:AZER OFF");       
writeline(d,"AVER OFF");
writeline(d,"DISP:DIG 4");           
writeline(d,"DISP:ENAB OFF");        


writeline(d,"FORM:ELEM READ,TIME");  % :contentReference[oaicite:9]{index=9}
writeline(d, sprintf("VOLT:NPLC %g", nplc));
writeline(d,"TRIG:SOUR IMM");

%% ===== 采集 =====
t0 = tic;

t = [];   % time(s)
v = [];   % voltage(V)

figure;
h = plot(nan,nan);
xlabel("Time (s)"); ylabel("Voltage (V)");
grid on;

lastSaved = 0;

while toc(t0) < T_total_s
    writeline(d, sprintf("TRIG:COUN %d", chunkN));

    resp = writeread(d,"READ?");    
    nums = parseCsvNumbers(resp);    % [v1,t1,v2,t2,...]

    if mod(numel(nums),2) ~= 0
        warning("Unexpected response: %s", resp);
        continue;
    end

    vv = nums(1:2:end);
    tt = nums(2:2:end);

  
    tt = (tt - tt(1)) + toc(t0);

    v = [v; vv(:)];
    t = [t; tt(:)];

    set(h,'XData',t,'YData',v);
    drawnow limitrate;

    if numel(v) - lastSaved >= saveEveryN
        data = [t, v];
        save("k6514_gpib.mat","data","idn");
        lastSaved = numel(v);
    end
end

data = [t, v];
save("k6514_gpib.mat","data","idn");
disp("Saved: k6514_gpib.mat");

%% ====== 辅助函数 ======
function nums = parseCsvNumbers(s)
    s = strtrim(s);
    if s == ""
        nums = [];
        return;
    end
    parts = regexp(s,'[,\s]+','split');
    nums = str2double(parts);
    nums = nums(~isnan(nums));
end

function cleanup6514(d)
    try, writeline(d,"DISP:ENAB ON"); end
    try, writeline(d,"SYST:AZER ON"); end
    try, writeline(d,"SYST:ZCOR OFF"); end
    try, writeline(d,"SYST:ZCH OFF"); end

    try, writeline(d,"SYST:LOC"); end

    clear d
end
