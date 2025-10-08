//+------------------------------------------------------------------+
//|                                           All-in-OneEA.mq5       |
//|  Ultimate Concurrent EA with 3 Modes:                            |
//|  1. File Bridge: Reads trade commands from local JSON files.     |
//|  2. Webhook POST: Polls a URL for trade commands.                |
//|  3. Copy Trade: Acts as a Master/Slave for a copy trade system.  |
//|     - Master mode sends signals for all trade actions             |
//|       (Open, Close, Modify SL/TP, Place/Cancel Pending).         |
//|                                                                  |
//|  FIXES & NEW                                                     |
//|  - Robust handling of multi-command JSON (array or single obj).  |
//|  - Per-channel toggle to close opposite side before MARKET open: |
//|      * Webhook_CloseOppositeBeforeOpen                           |
//|      * FileBridge_CloseOppositeBeforeOpen                        |
//|  - Do NOT affect manual/click trading; logic scoped by channel.  |
//+------------------------------------------------------------------+
#property strict

//==================== Inputs ====================
input group "=== Mode Activation ===";
input bool EnableFileBridgeMode  = false; // Enable/disable File Bridge mode
input bool EnableWebhookMode     = false; // Enable/disable Webhook POST mode
input bool EnableCopyTradeMode   = true;  // Enable/disable Copy Trade mode

// --- File Bridge Settings ---
input group "=== File Bridge Settings ===";
input bool   AutoLinkInstance    = true;
input string InstanceRootPath    = "C:\\Path\\To\\Your\\Instances";  // parent folder containing <ACCOUNT>\\MQL5\\Files
input string FilePattern         = "webhook_command_*.json";
input bool   DeleteAfterProcess  = true;
input bool   FileBridge_CloseOppositeBeforeOpen = false; // FILE BRIDGE ONLY: close opposite side first (MARKET only)

// --- Webhook POST Settings ---
input group "=== Webhook POST Settings ===";
input string WebhookURL          = "http://127.0.0.1:5000/webhook/TOKEN";
input int    HttpTimeoutMs       = 10000;
input bool   Webhook_CloseOppositeBeforeOpen = false; // WEBHOOK ONLY: close opposite side first (MARKET only)

// --- Copy Trading Settings ---
input group "=== Copy Trading Settings ===";
input string CopyApiEndpointUrl  = "https://your-api.com/api/trade";
input string CopyApiKey          = "PASTE_YOUR_KEY_HERE";
input int    CopyPollFrequency   = 2;

// --- General Settings ---
input group "=== General Settings (All Modes) ===";
input double DefaultVolume       = 0.10;
input int    Slippage            = 10;
input string TradeComment        = "WebhookEA";
input long   MagicNumberInput    = 0;   // 0 = auto from account
input int    PollingSeconds      = 1;   // Used by FileBridge/Webhook timers

//==================== Globals ====================
long   g_magic       = 0;
string g_instanceSub = "";
bool   g_readyFB     = false;
bool   g_directMode  = false;

//==================== Imports ====================
#import "shell32.dll"
int ShellExecuteW(int hwnd, string lpOperation, string lpFile, string lpParameters, string lpDirectory, int nShowCmd);
#import

//==================== Utils ======================
string ToLower(string s){ StringToLower(s); return s; }
long   ComputeAutoMagic(){ long lg=(long)AccountInfoInteger(ACCOUNT_LOGIN); if(lg<=0) return 999999; return lg%1000000; }
string DataFolder(){ return TerminalInfoString(TERMINAL_DATA_PATH); }
string FilesRoot(){ return DataFolder()+"\\MQL5\\Files"; }

string NormalizePath(string p){
   string q = p;
   StringToLower(q);
   StringReplace(q, "/", "\\");
   while(StringLen(q)>0 && StringGetCharacter(q,(int)StringLen(q)-1)=='\\')
      q = StringSubstr(q, 0, (int)StringLen(q)-1);
   return q;
}
bool FolderExistsUnderFiles(const string sub){
   string found=""; long h=FileFindFirst(sub+"\\*.*",found,0);
   if(h==INVALID_HANDLE) return false;
   FileFindClose(h); return true;
}
bool CreateJunction(const string dst_abs, const string src_abs){
   string cmd  = "C:\\Windows\\System32\\cmd.exe";
   string args = "/c mklink /J \"" + dst_abs + "\" \"" + src_abs + "\"";
   int r = ShellExecuteW(0,"runas",cmd,args,"",1);
   if(r>32) Print("Requested junction (mklink): ", dst_abs, " -> ", src_abs);
   else     Print("ShellExecute mklink failed.");
   return (r>32);
}

//==================== Robust JSON ====================
// Skip spaces/CRLF
int NextNonSpace(const string s, int i){
   int n=(int)StringLen(s);
   while(i<n){
      int ch=StringGetCharacter(s,i);
      if(ch!=' ' && ch!='\t' && ch!='\r' && ch!='\n') break;
      i++;
   }
   return i;
}
// Works with "key":"value", 'key':'value', numeric/bool; case-insensitive key
string GetVal(const string json, const string key){
   string jlow = json, klow = key;
   StringToLower(jlow); StringToLower(klow);

   int p = StringFind(jlow, "\""+klow+"\"");
   int token = (p!=-1) ? (int)StringLen(key)+2 : 0;
   if(p==-1){ p = StringFind(jlow, "'"+klow+"'"); if(p==-1) return ""; token=(int)StringLen(key)+2; }

   int colon = StringFind(json, ":", p+token);
   if(colon==-1) return "";
   int i = NextNonSpace(json, colon+1);
   int ch = StringGetCharacter(json,i);

   if(ch=='\"' || ch=='\''){
      int quote=ch; i++;
      int q=i, n=(int)StringLen(json);
      while(q<n && StringGetCharacter(json,q)!=quote) q++;
      if(q>=n) return "";
      return StringSubstr(json, i, q-i);
   }
   int q=i, n=(int)StringLen(json);
   while(q<n){
      ch=StringGetCharacter(json,q);
      if(ch==',' || ch=='}' || ch==']' || ch=='\r' || ch=='\n') break;
      q++;
   }
   string v=StringSubstr(json,i,q-i);
   StringTrimLeft(v); StringTrimRight(v);
   return v;
}

// Split top-level JSON into object items.
// Supports: single object "{...}"  OR array "[{...},{...}]"
// Returns number of items placed into 'items' array.
int SplitJsonObjects(const string json, string &items[])
{
   ArrayResize(items, 0);
   int n = (int)StringLen(json);
   int i = NextNonSpace(json, 0);
   if(i>=n) return 0;

   int ch = StringGetCharacter(json, i);

   // Case 1: single object
   if(ch=='{')
   {
      ArrayResize(items, 1);
      items[0] = json;
      return 1;
   }

   // Case 2: array of objects
   if(ch=='[')
   {
      bool inStr=false, esc=false;
      int depth=0; // braces depth {}
      int start=-1;
      for(int k=i+1; k<n; ++k)
      {
         int c = StringGetCharacter(json, k);

         if(inStr)
         {
            if(esc){ esc=false; continue; }
            if(c=='\\'){ esc=true; continue; }
            if(c=='"'){ inStr=false; }
            continue;
         }
         else
         {
            if(c=='"'){ inStr=true; continue; }
            if(c=='{')
            {
               if(depth==0) start=k;
               depth++;
            }
            else if(c=='}')
            {
               depth--;
               if(depth==0 && start>=0)
               {
                  int len = k - start + 1;
                  string obj = StringSubstr(json, start, len);
                  int sz = ArraySize(items);
                  ArrayResize(items, sz+1);
                  items[sz] = obj;
                  start = -1;
               }
            }
         }
      }
      return ArraySize(items);
   }

   // Fallback: treat as single object
   ArrayResize(items, 1);
   items[0] = json;
   return 1;
}

//==================== Symbol helpers ====================
string AlnumUpper(const string s){
   string out="";
   for(int i=0;i<(int)StringLen(s);++i){
      int ch = StringGetCharacter(s,i);
      if( (ch>='0' && ch<='9') || (ch>='A' && ch<='Z') || (ch>='a' && ch<='z') ){
         if(ch>='a' && ch<='z') ch = ch - 'a' + 'A';
         uchar uc8 = (uchar)ch; // ASCII only
         out += CharToString(uc8);
      }
   }
   return out;
}
string ResolveSymbol(const string want){
   if(want=="") return "";
   string base = want;

   if(SymbolSelect(base,true)) return base;

   string want_up = base; StringToUpper(want_up);
   for(int i=0;i<SymbolsTotal(false);++i){
      string s = SymbolName(i,false);
      string su=s; StringToUpper(su);
      if(su==want_up){ SymbolSelect(s,true); return s; }
   }

   string want_norm = AlnumUpper(base);
   int bestScore=-100000; string best="";
   for(int i=0;i<SymbolsTotal(false);++i){
      string s = SymbolName(i,false);
      string sn = AlnumUpper(s);
      int score = -1000;
      if(sn==want_norm) score=100;
      else{
         int pos = StringFind(sn,want_norm);
         if(pos==0)                           score = 90 - (int)(StringLen(sn)-StringLen(want_norm));
         else if(StringFind(want_norm,sn)==0) score = 80 - (int)(StringLen(want_norm)-StringLen(sn));
         else if(pos>=0)                      score = 70 - (int)(StringLen(sn)-StringLen(want_norm));
      }
      if(score>bestScore){ bestScore=score; best=s; }
   }
   if(best!=""){ SymbolSelect(best,true); return best; }

   for(int i=0;i<SymbolsTotal(true);++i){
      string s = SymbolName(i,true);
      if(StringFind(s, base)>=0){ SymbolSelect(s,true); return s; }
   }
   return "";
}

//==================== Trading ====================
double NormalizeLots(const string sym,double vol){
   double step=SymbolInfoDouble(sym,SYMBOL_VOLUME_STEP);
   double vmin=SymbolInfoDouble(sym,SYMBOL_VOLUME_MIN);
   double vmax=SymbolInfoDouble(sym,SYMBOL_VOLUME_MAX);
   if(step>0 && vmin>0){ vol=MathMax(vmin, MathFloor(vol/step)*step); vol=MathMin(vol,vmax); }
   return vol;
}

// Close all positions of a specific side (BUY/SELL) for a symbol
bool ClosePositionsByType(const string sym, const ENUM_POSITION_TYPE typToClose)
{
   string realSym = ResolveSymbol(sym);
   if(realSym==""){ Print("CLOSE-BY-TYPE: cannot resolve '", sym, "'"); return false; }

   bool any=false;
   for(int i=PositionsTotal()-1; i>=0; --i){
      ulong ticket = PositionGetTicket(i);
      if(!PositionSelectByTicket(ticket)) continue;
      if(PositionGetString(POSITION_SYMBOL)!=realSym) continue;
      if((ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE)!=typToClose) continue;

      double vol = PositionGetDouble(POSITION_VOLUME);
      double price = (typToClose==POSITION_TYPE_BUY)
                     ? SymbolInfoDouble(realSym, SYMBOL_BID)
                     : SymbolInfoDouble(realSym, SYMBOL_ASK);

      MqlTradeRequest req;  ZeroMemory(req);
      MqlTradeResult  res;  ZeroMemory(res);

      req.action       = TRADE_ACTION_DEAL;
      req.symbol       = realSym;
      req.volume       = vol;
      req.price        = price;
      req.deviation    = Slippage;
      req.magic        = (MagicNumberInput>0?MagicNumberInput:ComputeAutoMagic());
      req.type_filling = ORDER_FILLING_FOK;
      req.position     = ticket;
      req.type         = (typToClose==POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;

      ResetLastError();
      if(OrderSend(req,res)){
         any=true;
         PrintFormat("CLOSE-BY-TYPE OK ticket=%I64u vol=%.2f", ticket, vol);
      }else{
         PrintFormat("CLOSE-BY-TYPE FAIL ticket=%I64u ret=%d err=%d comment=%s",
                     ticket, res.retcode, GetLastError(), res.comment);
      }
   }
   return any;
}

// Send orders: market + pending (limit/stop) with TP/SL
bool SendOrderAdvanced(string action, string order_type, string sym,
                       double volume, double price, double sl, double tp,
                       string comment, string exp_iso)
{
   string realSym = ResolveSymbol(sym);
   if(realSym==""){ Print("ABORT: cannot resolve symbol from '",sym,"'"); return false; }

   MqlTick t; if(!SymbolInfoTick(realSym,t)){ Print("ABORT: no tick for ",realSym," err=",GetLastError()); return false; }

   double useLots = NormalizeLots(realSym, (volume>0?volume:DefaultVolume));
   if(useLots<=0){ Print("ABORT: lot is zero after normalize for ",realSym); return false; }

   int digits=(int)SymbolInfoInteger(realSym,SYMBOL_DIGITS);
   double pnorm=(price>0 ? NormalizeDouble(price,digits) : 0.0);
   double sln  =(sl>0    ? NormalizeDouble(sl,digits)    : 0.0);
   double tpn  =(tp>0    ? NormalizeDouble(tp,digits)    : 0.0);

   string act=ToLower(action), ot=ToLower(order_type);
   if(act=="long")  act="buy";
   if(act=="short") act="sell";

   MqlTradeRequest req;  ZeroMemory(req);
   MqlTradeResult  res;  ZeroMemory(res);
   req.symbol       = realSym;
   req.volume       = useLots;
   req.magic        = (MagicNumberInput>0?MagicNumberInput:ComputeAutoMagic());
   req.comment      = comment;
   req.deviation    = Slippage;
   req.sl           = sln;
   req.tp           = tpn;

   if(ot=="" || ot=="market")
   {
      req.action       = TRADE_ACTION_DEAL;
      req.type_filling = ORDER_FILLING_FOK;
      if(act=="buy"){ req.type=ORDER_TYPE_BUY;  req.price=t.ask; }
      else          { req.type=ORDER_TYPE_SELL; req.price=t.bid; }
   }
   else
   {
      if(pnorm<=0){ Print("ABORT: pending needs 'price' > 0"); return false; }

      if(ot=="limit" || ot=="stop")
         ot = (act=="buy" ? "buy_"+ot : "sell_"+ot);

      if(ot=="buy_limit")       req.type=ORDER_TYPE_BUY_LIMIT;
      else if(ot=="sell_limit") req.type=ORDER_TYPE_SELL_LIMIT;
      else if(ot=="buy_stop")   req.type=ORDER_TYPE_BUY_STOP;
      else if(ot=="sell_stop")  req.type=ORDER_TYPE_SELL_STOP;
      else { Print("ABORT: unknown order_type='",order_type,"'"); return false; }

      if(req.type==ORDER_TYPE_BUY_LIMIT  && !(pnorm < t.ask)) { Print("ABORT: BUY_LIMIT price must be < Ask"); return false; }
      if(req.type==ORDER_TYPE_SELL_LIMIT && !(pnorm > t.bid)) { Print("ABORT: SELL_LIMIT price must be > Bid"); return false; }
      if(req.type==ORDER_TYPE_BUY_STOP   && !(pnorm > t.ask)) { Print("ABORT: BUY_STOP  price must be > Ask"); return false; }
      if(req.type==ORDER_TYPE_SELL_STOP  && !(pnorm < t.bid)) { Print("ABORT: SELL_STOP price must be < Bid"); return false; }

      req.action    = TRADE_ACTION_PENDING;
      req.price     = pnorm;
      req.type_time = ORDER_TIME_GTC;

      if(StringLen(exp_iso)>0){
         string d=exp_iso; StringReplace(d,"T"," "); StringReplace(d,"Z",""); StringReplace(d,"-",".");
         datetime exp = StringToTime(d);
         if(exp>0){ req.type_time = ORDER_TIME_SPECIFIED; req.expiration = exp; }
      }
   }

   ResetLastError();
   bool ok=OrderSend(req,res);
   if(!ok){
      PrintFormat("ORDER FAIL type=%d sym=%s price=%.5f lots=%.2f ret=%d err=%d comment=%s",
                  req.type, realSym, req.price, useLots, res.retcode, GetLastError(), res.comment);
      return false;
   }
   PrintFormat("ORDER OK type=%d ticket=%I64d sym=%s price=%.5f lots=%.2f",
               req.type, res.order, realSym, res.price, useLots);
   return true;
}

// Close by amount: if <=0 or >= total, close all
bool ClosePositionsByAmount(string sym, double reqVolume)
{
   string realSym = ResolveSymbol(sym);
   if(realSym==""){ Print("CLOSE: cannot resolve symbol '", sym, "'"); return false; }

   double totalVol=0.0;
   for(int i=PositionsTotal()-1; i>=0; --i){
      if(!PositionSelectByTicket(PositionGetTicket(i))) continue;
      if(PositionGetString(POSITION_SYMBOL) != realSym) continue;
      totalVol += PositionGetDouble(POSITION_VOLUME);
   }
   if(totalVol<=0.0){ Print("CLOSE: no positions for ", realSym); return true; }

   double target = reqVolume;
   if(target<=0.0 || target>=totalVol-1e-8) target = totalVol;

   double remaining = target;
   bool any=false;

   for(int i=PositionsTotal()-1; i>=0 && remaining>0.0; --i)
   {
      ulong ticket = PositionGetTicket(i);
      if(!PositionSelectByTicket(ticket)) continue;
      if(PositionGetString(POSITION_SYMBOL) != realSym) continue;

      ENUM_POSITION_TYPE typ = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      double posVol = PositionGetDouble(POSITION_VOLUME);
      double lotsToClose = MathMin(posVol, remaining);

      double price = (typ==POSITION_TYPE_BUY)
                     ? SymbolInfoDouble(realSym, SYMBOL_BID)
                     : SymbolInfoDouble(realSym, SYMBOL_ASK);

      MqlTradeRequest req;  ZeroMemory(req);
      MqlTradeResult  res;  ZeroMemory(res);

      req.action       = TRADE_ACTION_DEAL;
      req.symbol       = realSym;
      req.volume       = lotsToClose;
      req.price        = price;
      req.deviation    = Slippage;
      req.magic        = (MagicNumberInput>0?MagicNumberInput:ComputeAutoMagic());
      req.type_filling = ORDER_FILLING_FOK;
      req.position     = (ulong)ticket;
      req.type         = (typ==POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;

      ResetLastError();
      if(OrderSend(req,res)){
         any=true;
         remaining -= lotsToClose;
         PrintFormat("CLOSE OK ticket=%I64u closed=%.2f remain=%.2f", ticket, lotsToClose, remaining);
      }else{
         PrintFormat("CLOSE FAIL ticket=%I64u ret=%d err=%d comment=%s",
                     ticket, res.retcode, GetLastError(), res.comment);
      }
   }

   if(!any) Print("CLOSE: unable to close any position for ", realSym);
   return any;
}

//==================== File IO ====================
bool ReadAllText(const string path,string &out){
   int h = FileOpen(path, FILE_READ|FILE_BIN);
   if(h==INVALID_HANDLE) return false;

   uint sz = (uint)FileSize(h);
   if(sz==0){ FileClose(h); out=""; return true; }

   char data[];
   ArrayResize(data, (int)sz);
   int n = FileReadArray(h, data, 0, (int)sz);
   FileClose(h);

   if(n<=0){ out=""; return true; }

   int start=0;
   if(n>=3 && (uchar)data[0]==0xEF && (uchar)data[1]==0xBB && (uchar)data[2]==0xBF) start=3;

   out = CharArrayToString(data, start, n-start);
   return true;
}
void CleanupFile(const string full){ if(DeleteAfterProcess) FileDelete(full); }

//==================== File Bridge ====================
bool ProcessFromPath(const string base){
   string mask = (base=="" ? FilePattern : base + "\\" + FilePattern);
   string found=""; long h=FileFindFirst(mask, found, 0);
   if(h==INVALID_HANDLE) return false;
   FileFindClose(h);
   if(found=="") return false;

   string full = (base=="" ? found : base + "\\" + found);
   string js; if(!ReadAllText(full,js)){ Print("Cannot read ",full," err=",GetLastError()); return true; }

   // Split into top-level command objects (a single file may contain multiple commands)
   string cmds[]; int cnt = SplitJsonObjects(js, cmds);
   if(cnt<=0){ Print("FILEBRIDGE: invalid json in ", found); CleanupFile(full); return true; }
   if(cnt>1)  PrintFormat("FILEBRIDGE: %d commands found in %s", cnt, found);

   for(int idx=0; idx<cnt; ++idx)
   {
      string obj = cmds[idx];

      string sym=GetVal(obj,"broker_symbol"); if(sym=="") sym=GetVal(obj,"symbol"); if(sym=="") sym=GetVal(obj,"original_symbol");
      string action=ToLower(GetVal(obj,"action"));
      if(action=="long")  action="buy";
      if(action=="short") action="sell";
      string otype =ToLower(GetVal(obj,"order_type"));
      string comment=GetVal(obj,"comment"); if(comment=="") comment=TradeComment;
      double vol = StringToDouble(GetVal(obj,"volume")); if(vol<=0) vol=DefaultVolume;

      string tp_s = GetVal(obj,"tp"); if(tp_s=="") tp_s=GetVal(obj,"take_profit");
      string sl_s = GetVal(obj,"sl"); if(sl_s=="") sl_s=GetVal(obj,"stop_loss");
      double tp = StringToDouble(tp_s);
      double sl = StringToDouble(sl_s);
      double price = StringToDouble(GetVal(obj,"price"));
      string exp   = GetVal(obj,"expiration");

      string cmdtype = ToLower(GetVal(obj,"command_type"));
      if(action=="close" || cmdtype=="close_position"){
         double reqVol = StringToDouble(GetVal(obj,"volume"));
         ClosePositionsByAmount(sym, reqVol);
         continue;
      }

      if(action!="buy" && action!="sell"){
         Print("FILEBRIDGE: unknown action in ",found,": ",action); 
         continue;
      }

      // FILE-BRIDGE ONLY toggle (market only)
      if(FileBridge_CloseOppositeBeforeOpen && (otype=="" || otype=="market"))
      {
         ENUM_POSITION_TYPE toClose = (action=="buy") ? POSITION_TYPE_SELL : POSITION_TYPE_BUY;
         ClosePositionsByType(sym, toClose);
      }

      SendOrderAdvanced(action, otype, sym, vol, price, sl, tp, comment, exp);
   }

   CleanupFile(full);
   return true;
}
void ProcessOneFile(){
   if(!g_readyFB) return;
   if(g_instanceSub!="" && ProcessFromPath(g_instanceSub)) return; // instance_<account>
   ProcessFromPath("");                                            // root of MQL5\\Files
}

//==================== Webhook (POST JSON) & Copy Trading Communication ====================
int PostJSON(const string url, const string json, string &resp){
   string headers="Content-Type: application/json\r\n";
   if(EnableCopyTradeMode && CopyApiKey != "")
   {
      headers += "Authorization: Bearer " + CopyApiKey + "\r\n";
   }
   char data[]; StringToCharArray(json,data);
   char result[]; string rh;
   ResetLastError();
   int code=WebRequest("POST",url,headers,HttpTimeoutMs,data,result,rh);
   if(code==200 || code==201) resp=CharArrayToString(result); else resp="";
   PrintFormat("WEBREQUEST to %s, code=%d, lastError=%d", url, code, GetLastError());
   return code;
}
void PollWebhook(){
   string req="{\"ping\":1}";
   string resp=""; int code=PostJSON(WebhookURL,req,resp);
   if(code!=200 || resp=="") return;

   // Split into top-level command objects
   string cmds[]; int cnt = SplitJsonObjects(resp, cmds);
   if(cnt<=0){ Print("WEBHOOK: no command objects found"); return; }
   if(cnt>1)  PrintFormat("WEBHOOK: %d commands received in one response", cnt);

   for(int idx=0; idx<cnt; ++idx)
   {
      string obj = cmds[idx];

      string sym=GetVal(obj,"broker_symbol"); if(sym=="") sym=GetVal(obj,"symbol"); if(sym=="") sym=GetVal(obj,"original_symbol");
      string action=ToLower(GetVal(obj,"action"));
      if(action=="long")  action="buy";
      if(action=="short") action="sell";
      string otype=ToLower(GetVal(obj,"order_type"));
      string comment=GetVal(obj,"comment"); if(comment=="") comment=TradeComment;
      double vol=StringToDouble(GetVal(obj,"volume")); if(vol<=0) vol=DefaultVolume;

      string tp_s=GetVal(obj,"tp"); if(tp_s=="") tp_s=GetVal(obj,"take_profit");
      string sl_s=GetVal(obj,"sl"); if(sl_s=="") sl_s=GetVal(obj,"stop_loss");
      double tp=StringToDouble(tp_s), sl=StringToDouble(sl_s);
      double price=StringToDouble(GetVal(obj,"price"));
      string exp=GetVal(obj,"expiration");

      string cmdtype = ToLower(GetVal(obj,"command_type"));
      if(action=="close" || cmdtype=="close_position"){
         double reqVol=StringToDouble(GetVal(obj,"volume"));
         ClosePositionsByAmount(sym, reqVol);
         continue;
      }

      if(action!="buy" && action!="sell"){
         Print("WEBHOOK: unknown action: ",action); 
         continue;
      }

      // WEBHOOK ONLY toggle (market only)
      if(Webhook_CloseOppositeBeforeOpen && (otype=="" || otype=="market"))
      {
         ENUM_POSITION_TYPE toClose = (action=="buy") ? POSITION_TYPE_SELL : POSITION_TYPE_BUY;
         ClosePositionsByType(sym, toClose);
      }

      SendOrderAdvanced(action, otype, sym, vol, price, sl, tp, comment, exp);
   }
}

//==================== Copy Trading Logic ====================
void ProcessCopyTradeSlave()
{
   long acc_num = AccountInfoInteger(ACCOUNT_LOGIN);
   string json_body = "{\"accountNumber\":" + IntegerToString(acc_num) + "}";
   string response = "";

   int code = PostJSON(CopyApiEndpointUrl, json_body, response);
   if(code != 200 || response == "" || response == "{}") return;

   Print("CopyTrade Slave received command: ", response);

   string sym     = GetVal(response,"symbol");
   string action  = ToLower(GetVal(response,"action"));
   string otype   = ToLower(GetVal(response,"order_type"));
   double vol     = StringToDouble(GetVal(response,"volume"));
   double price   = StringToDouble(GetVal(response,"price"));
   double sl      = StringToDouble(GetVal(response,"sl"));
   double tp      = StringToDouble(GetVal(response,"tp"));
   string comment = GetVal(response,"comment"); if(comment=="") comment = TradeComment;

   if(action == "close"){
      ClosePositionsByAmount(sym, vol);
   }else if(action == "buy" || action == "sell"){
      SendOrderAdvanced(action, otype, sym, vol, price, sl, tp, comment, "");
   }
}

void SendCopyTradeMasterSignal_Position(long ticket, string event_type)
{
   if(!PositionSelectByTicket(ticket)) return;

   string symbol    = PositionGetString(POSITION_SYMBOL);
   string type_str  = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? "buy" : "sell");
   double volume    = PositionGetDouble(POSITION_VOLUME);
   double price     = PositionGetDouble(POSITION_PRICE_OPEN);
   double sl        = PositionGetDouble(POSITION_SL);
   double tp        = PositionGetDouble(POSITION_TP);
   long acc_num     = AccountInfoInteger(ACCOUNT_LOGIN);

   string json_body = "{";
   json_body += "\"accountNumber\":" + IntegerToString(acc_num) + ",";
   json_body += "\"event\":\"" + event_type + "\",";
   json_body += "\"dataType\":\"position\",";
   json_body += "\"symbol\":\"" + symbol + "\",";
   json_body += "\"action\":\"" + type_str + "\",";
   json_body += "\"volume\":" + DoubleToString(volume, 8) + ",";
   json_body += "\"price\":" + DoubleToString(price, 5) + ",";
   json_body += "\"sl\":" + DoubleToString(sl, 5) + ",";
   json_body += "\"tp\":" + DoubleToString(tp, 5) + ",";
   json_body += "\"ticket\":" + IntegerToString(ticket);
   json_body += "}";

   string response = "";
   Print("CopyTrade Master sending POSITION signal: ", json_body);
   PostJSON(CopyApiEndpointUrl, json_body, response);
}

void SendCopyTradeMasterSignal_Order(long ticket, string event_type)
{
   if(!OrderSelect(ticket)) return;

   string symbol    = OrderGetString(ORDER_SYMBOL);
   string type_str  = "";
   switch((ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE))
   {
      case ORDER_TYPE_BUY_LIMIT:  type_str = "buy_limit"; break;
      case ORDER_TYPE_SELL_LIMIT: type_str = "sell_limit"; break;
      case ORDER_TYPE_BUY_STOP:   type_str = "buy_stop"; break;
      case ORDER_TYPE_SELL_STOP:  type_str = "sell_stop"; break;
      default: type_str = "unknown"; break;
   }
   double volume    = OrderGetDouble(ORDER_VOLUME_INITIAL);
   double price     = OrderGetDouble(ORDER_PRICE_OPEN);
   double sl        = OrderGetDouble(ORDER_SL);
   double tp        = OrderGetDouble(ORDER_TP);
   long acc_num     = AccountInfoInteger(ACCOUNT_LOGIN);

   string json_body = "{";
   json_body += "\"accountNumber\":" + IntegerToString(acc_num) + ",";
   json_body += "\"event\":\"" + event_type + "\",";
   json_body += "\"dataType\":\"order\",";
   json_body += "\"symbol\":\"" + symbol + "\",";
   json_body += "\"action\":\"" + type_str + "\",";
   json_body += "\"volume\":" + DoubleToString(volume, 8) + ",";
   json_body += "\"price\":" + DoubleToString(price, 5) + ",";
   json_body += "\"sl\":" + DoubleToString(sl, 5) + ",";
   json_body += "\"tp\":" + DoubleToString(tp, 5) + ",";
   json_body += "\"ticket\":" + IntegerToString(ticket);
   json_body += "}";

   string response = "";
   Print("CopyTrade Master sending ORDER signal: ", json_body);
   PostJSON(CopyApiEndpointUrl, json_body, response);
}

//==================== EA Lifecycle ====================
int OnInit(){
   g_magic = (MagicNumberInput > 0 ? MagicNumberInput : ComputeAutoMagic());
   PrintFormat("TradingWebhookEA (Concurrent) started. Magic=%I64d", g_magic);
   if(EnableFileBridgeMode) Print("- FileBridge Mode: ENABLED");
   if(EnableWebhookMode)    Print("- Webhook Mode: ENABLED");
   if(EnableCopyTradeMode)  Print("- CopyTrade Mode: ENABLED");

   if(EnableFileBridgeMode){
      int acc=(int)AccountInfoInteger(ACCOUNT_LOGIN);
      string accStr=IntegerToString(acc);

      string src = InstanceRootPath + "\\" + accStr + "\\MQL5\\Files";
      string df  = TerminalInfoString(TERMINAL_DATA_PATH);
      string fr  = FilesRoot();
      string dst = df + "\\MQL5\\Files\\instance_" + accStr;

      g_directMode = (NormalizePath(src) == NormalizePath(fr));
      if(g_directMode){
         g_instanceSub = "";
         g_readyFB     = true;
         Print("DIRECT MODE: DataFolder matches SRC. Reading from MQL5\\Files root.");
      }else{
         g_instanceSub = "instance_" + accStr;
         Print("DataFolder=", df);
         Print("SRC=", src);
         Print("DST=", dst);

         if(AutoLinkInstance){
            if(!FolderExistsUnderFiles(g_instanceSub)){
               Print("Instance junction not found. Creating...");
               CreateJunction(dst, src);
            } else {
               Print("Instance junction exists: ", g_instanceSub);
            }
         }
         g_readyFB = FolderExistsUnderFiles(g_instanceSub);
         if(!g_readyFB) Print("WARNING: FileBridge not ready. Folder missing: ", g_instanceSub);
      }
   }

   int shortestInterval = 9999;
   if(EnableFileBridgeMode || EnableWebhookMode) shortestInterval = MathMin(shortestInterval, PollingSeconds);
   if(EnableCopyTradeMode)                      shortestInterval = MathMin(shortestInterval, CopyPollFrequency);
   if(shortestInterval < 9999) EventSetTimer(MathMax(1, shortestInterval));

   return(INIT_SUCCEEDED);
}

void OnDeinit(const int r){ EventKillTimer(); }

void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
{
   if(!EnableCopyTradeMode) return;

   if(trans.type == TRADE_TRANSACTION_DEAL_ADD)
   {
      Print("Master Event: DEAL_ADD for position #", trans.position);
      SendCopyTradeMasterSignal_Position((long)trans.position, "deal_add");
   }

   if(trans.type == TRADE_TRANSACTION_ORDER_UPDATE)
   {
      if(PositionSelectByTicket(trans.position))
      {
         Print("Master Event: ORDER_UPDATE for position #", trans.position);
         SendCopyTradeMasterSignal_Position((long)trans.position, "deal_update");
      }
      else if(OrderSelect(trans.order))
      {
         Print("Master Event: ORDER_UPDATE for pending order #", trans.order);
         SendCopyTradeMasterSignal_Order((long)trans.order, "order_update");
      }
   }

   if(trans.type == TRADE_TRANSACTION_ORDER_ADD)
   {
      if(OrderSelect(trans.order))
      {
         Print("Master Event: ORDER_ADD (New Pending) for order #", trans.order);
         SendCopyTradeMasterSignal_Order((long)trans.order, "order_add");
      }
   }

   if(trans.type == TRADE_TRANSACTION_ORDER_DELETE)
   {
      Print("Master Event: ORDER_DELETE (Cancel Pending) for order #", trans.order);
      long acc_num = AccountInfoInteger(ACCOUNT_LOGIN);
      string json_body = StringFormat("{\"accountNumber\":%d,\"event\":\"order_cancel\",\"dataType\":\"order\",\"ticket\":%d}", acc_num, trans.order);
      string response;
      PostJSON(CopyApiEndpointUrl, json_body, response);
   }
}

void OnTimer(){
   if(EnableFileBridgeMode)  ProcessOneFile();
   if(EnableWebhookMode)     PollWebhook();
   if(EnableCopyTradeMode)   ProcessCopyTradeSlave();
}

