//+------------------------------------------------------------------+
//|                                        AllInOneTradingEA.mq5     |
//|                    Multi-Mode: Webhook + Master + Slave          |
//|  v2.0 - Support concurrent execution of multiple modes           |
//+------------------------------------------------------------------+
#property copyright "MT5 Trading Bot"
#property link      "https://github.com/Jayferj"
#property version   "2.01"
#property strict

//==================== Enums ====================
enum ENUM_LOG_LEVEL
{
   LOG_DEBUG,        // Debug (All messages)
   LOG_INFO,         // Info (Important events)
   LOG_WARNING,      // Warning (Potential issues)
   LOG_ERROR         // Error (Critical issues only)
};

//==================== Input Parameters ====================
input group "=== Mode Selection (Multi-Select) ==="
input bool EnableWebhook = false;                          // ? Enable Webhook Mode
input bool EnableMaster = false;                           // ? Enable Master Mode
input bool EnableSlave = false;                            // ? Enable Slave Mode

input group "=== Webhook Settings ==="
input bool WebhookCloseOppositeBeforeOpen = false;   // Close opposite positions before opening (Webhook)

input bool   Webhook_AutoLinkInstance = true;              // Auto-link instance folder
input string Webhook_InstanceRootPath = "C:\\trading_bot\\mt5_instances"; // Instance root path
input string Webhook_FilePattern = "webhook_command_*.json"; // Command file pattern
input int    Webhook_PollingSeconds = 1;                   // File check interval (seconds)
input bool   Webhook_DeleteAfterProcess = true;            // Delete file after execution

input group "=== Master Settings ==="
input string Master_ServerURL = "http://localhost:5000";   // Server URL
input string Master_APIKey = "";                           // API Key (from Copy Pair)
input bool   Master_SendOnOpen = true;                     // Send signal on position open
input bool   Master_SendOnClose = true;                    // Send signal on position close
input bool   Master_SendOnModify = true;                   // Send signal on TP/SL modify
input int    Master_HttpTimeoutMs = 10000;                 // HTTP timeout (ms)

input group "=== Slave Settings ==="
input bool   Slave_AutoLinkInstance = true;                // Auto-link instance folder
input string Slave_InstanceRootPath = "C:\\trading_bot\\mt5_instances"; // Instance root path
input string Slave_FilePattern = "slave_command_*.json"; // Command file pattern
input int    Slave_PollingSeconds = 1;                     // File check interval (seconds)
input bool   Slave_DeleteAfterProcess = true;              // Delete file after execution

input group "=== Trade Settings ==="
input double DefaultVolume = 0.10;                         // Default volume
input int    Slippage = 10;                                // Slippage (points)
input string TradeComment = "AllInOneEA";                  // Trade comment
input long   MagicNumberInput = 0;                         // Magic number (0 = auto)

input group "=== Logging ==="
input bool EnableLogging = true;                           // Enable logging
input ENUM_LOG_LEVEL LogLevel = LOG_INFO;                  // Log level

//==================== Global Variables ====================
string AccountNumber;
long   g_magic = 0;
bool   Initialized = false;

// Webhook globals
string g_webhook_instanceSub = "";
bool   g_webhook_readyFB = false;
bool   g_webhook_directMode = false;

// Slave globals
string g_slave_instanceSub = "";
bool   g_slave_readyFB = false;
bool   g_slave_directMode = false;

// Master tracking arrays
ulong MasterTickets[];
string MasterSymbols[];
int MasterTypes[];
double MasterVolumes[];
double MasterTPs[];
double MasterSLs[];

// Thread-safe counter for concurrent processing
int g_processing_counter = 0;

//==================== Imports ====================
#import "shell32.dll"
int ShellExecuteW(int hwnd, string lpOperation, string lpFile, string lpParameters, string lpDirectory, int nShowCmd);
#import

//==================== Utility Functions ====================
string ToLower(string s) { StringToLower(s); return s; }
long ComputeAutoMagic() { 
   long lg = (long)AccountInfoInteger(ACCOUNT_LOGIN);
   if(lg <= 0) return 999999;
   return lg % 1000000;
}
string DataFolder() { return TerminalInfoString(TERMINAL_DATA_PATH); }
string FilesRoot() { return DataFolder() + "\\MQL5\\Files"; }

string NormalizePath(string p) {
   string q = p;
   StringToLower(q);
   StringReplace(q, "/", "\\");
   while(StringLen(q) > 0 && StringGetCharacter(q, (int)StringLen(q)-1) == '\\')
      q = StringSubstr(q, 0, (int)StringLen(q)-1);
   return q;
}

bool FolderExistsUnderFiles(const string sub) {
   string found = "";
   long h = FileFindFirst(sub + "\\*", found, 0);
   bool exists = (h != INVALID_HANDLE);
   if(exists) FileFindClose(h);
   return exists;
}

void CreateJunction(string dst, string src) {
   string cmd = "/C mklink /J \"" + dst + "\" \"" + src + "\"";
   ShellExecuteW(0, "open", "cmd.exe", cmd, NULL, 0);
   Sleep(1000);
}

string ResolveSymbol(string sym) {
   if(sym == "") return "";
   if(SymbolSelect(sym, true)) return sym;
   
   string alt = sym;
   StringReplace(alt, "M", "");
   if(alt != sym && SymbolSelect(alt, true)) return alt;
   
   string suffixes[] = {".", ".a", "m", "M", "#"};
   for(int i = 0; i < ArraySize(suffixes); ++i) {
      if(StringFind(sym, suffixes[i]) >= 0) {
         string bare = sym;
         StringReplace(bare, suffixes[i], "");
         if(SymbolSelect(bare, true)) return bare;
      }
   }
   
   return "";
}

string GetVal(const string &js, const string &key) {
   string k = "\"" + key + "\"";
   int pos = StringFind(js, k);
   if(pos < 0) return "";
   
   int colPos = StringFind(js, ":", pos);
   if(colPos < 0) return "";
   
   int start = colPos + 1;
   while(start < StringLen(js)) {
      ushort c = StringGetCharacter(js, start);
      if(c != ' ' && c != '\t' && c != '\r' && c != '\n') break;
      start++;
   }
   
   if(start >= StringLen(js)) return "";
   
   ushort first = StringGetCharacter(js, start);
   if(first == '"') {
      int end = StringFind(js, "\"", start + 1);
      if(end < 0) return "";
      return StringSubstr(js, start + 1, end - start - 1);
   }
   
   int end = start;
   while(end < StringLen(js)) {
      ushort c = StringGetCharacter(js, end);
      if(c == ',' || c == '}' || c == ' ' || c == '\t' || c == '\r' || c == '\n') break;
      end++;
   }
   
   return StringSubstr(js, start, end - start);
}

//==================== Trading Functions ====================
bool SendOrderAdvanced(string action, string order_type, string sym, double volume, double price, double sl, double tp, string comment, string expire, string source) {
   g_processing_counter++;
   int process_id = g_processing_counter;
   
   LogMessage(LOG_DEBUG, "[" + IntegerToString(process_id) + "] Processing " + source + " order: " + action + " " + sym);
   
   string realSym = ResolveSymbol(sym);
   if(realSym == "") {
      LogMessage(LOG_ERROR, "[" + IntegerToString(process_id) + "] Cannot resolve symbol: " + sym);
      return false;
   }
   
   if(!SymbolSelect(realSym, true)) {
      LogMessage(LOG_ERROR, "[" + IntegerToString(process_id) + "] Cannot select symbol: " + realSym);
      return false;
   }
   
   MqlTick t;
   if(!SymbolInfoTick(realSym, t)) {
      LogMessage(LOG_ERROR, "[" + IntegerToString(process_id) + "] Cannot get tick for " + realSym);
      return false;
   }
   
   double minLot = SymbolInfoDouble(realSym, SYMBOL_VOLUME_MIN);
   double maxLot = SymbolInfoDouble(realSym, SYMBOL_VOLUME_MAX);
   double stepLot = SymbolInfoDouble(realSym, SYMBOL_VOLUME_STEP);
   
   double useLots = NormalizeDouble(MathMax(minLot, volume > 0 ? volume : DefaultVolume), 2);
   if(useLots <= 0) {
      LogMessage(LOG_ERROR, "[" + IntegerToString(process_id) + "] Volume is zero after normalization");
      return false;
   }
   
   int digits = (int)SymbolInfoInteger(realSym, SYMBOL_DIGITS);
   double pnorm = (price > 0 ? NormalizeDouble(price, digits) : 0.0);
   double sln = (sl > 0 ? NormalizeDouble(sl, digits) : 0.0);
   double tpn = (tp > 0 ? NormalizeDouble(tp, digits) : 0.0);
   
   string act = ToLower(action), ot = ToLower(order_type);
   if(act == "long") act = "buy";
   if(act == "short") act = "sell";
   
   if(source == "WEBHOOK" && WebhookCloseOppositeBeforeOpen && (act == "buy" || act == "sell")) {
      CloseOppositePositionsBySymbol(realSym, act, "WEBHOOK");
   }
   
   MqlTradeRequest req;
   ZeroMemory(req);
   MqlTradeResult res;
   ZeroMemory(res);
   
   req.symbol = realSym;
   req.volume = useLots;
   req.magic = (MagicNumberInput > 0 ? MagicNumberInput : ComputeAutoMagic());
   req.comment = (comment != "" ? comment : TradeComment + "_" + source);
   req.deviation = Slippage;
   req.sl = sln;
   req.tp = tpn;
   
   if(ot == "" || ot == "market") {
      req.action = TRADE_ACTION_DEAL;
      req.type_filling = ORDER_FILLING_FOK;
      if(act == "buy") {
         req.type = ORDER_TYPE_BUY;
         req.price = t.ask;
      } else {
         req.type = ORDER_TYPE_SELL;
         req.price = t.bid;
      }
   } else {
      if(pnorm <= 0) {
         LogMessage(LOG_ERROR, "[" + IntegerToString(process_id) + "] Pending order needs price > 0");
         return false;
      }
      
      if(ot == "limit" || ot == "stop")
         ot = (act == "buy" ? "buy_" + ot : "sell_" + ot);
      
      if(ot == "buy_limit") req.type = ORDER_TYPE_BUY_LIMIT;
      else if(ot == "sell_limit") req.type = ORDER_TYPE_SELL_LIMIT;
      else if(ot == "buy_stop") req.type = ORDER_TYPE_BUY_STOP;
      else if(ot == "sell_stop") req.type = ORDER_TYPE_SELL_STOP;
      else {
         LogMessage(LOG_ERROR, "[" + IntegerToString(process_id) + "] Unknown order_type: " + order_type);
         return false;
      }
      
      req.action = TRADE_ACTION_PENDING;
      req.price = pnorm;
      req.type_time = ORDER_TIME_GTC;
   }
   
   ResetLastError();
   bool ok = OrderSend(req, res);
   if(!ok) {
      LogMessage(LOG_ERROR, "[" + IntegerToString(process_id) + "] Order failed: ret=" + IntegerToString(res.retcode) + " err=" + IntegerToString(GetLastError()) + " " + res.comment);
      return false;
   }
   
   LogMessage(LOG_INFO, "[" + IntegerToString(process_id) + "] Order executed: " + act + " " + realSym + " " + DoubleToString(useLots, 2) + " @ " + DoubleToString(res.price, 5));
   return true;
}

bool ClosePositionsByAmount(string sym, double reqVolume, string source = "") {
   g_processing_counter++;
   int process_id = g_processing_counter;
   
   LogMessage(LOG_DEBUG, "[" + IntegerToString(process_id) + "] Processing " + source + " close: " + sym);
   
   string realSym = ResolveSymbol(sym);
   if(realSym == "") {
      LogMessage(LOG_ERROR, "[" + IntegerToString(process_id) + "] Cannot resolve symbol: " + sym);
      return false;
   }
   
   double totalVol = 0.0;
   for(int i = PositionsTotal() - 1; i >= 0; --i) {
      if(!PositionSelectByTicket(PositionGetTicket(i))) continue;
      if(PositionGetString(POSITION_SYMBOL) != realSym) continue;
      totalVol += PositionGetDouble(POSITION_VOLUME);
   }
   
   if(totalVol <= 0.0) {
      LogMessage(LOG_INFO, "[" + IntegerToString(process_id) + "] No positions to close for " + realSym);
      return true;
   }
   
   double target = reqVolume;
   if(target <= 0.0 || target >= totalVol - 1e-8) target = totalVol;
   
   double remaining = target;
   bool any = false;
   
   for(int i = PositionsTotal() - 1; i >= 0 && remaining > 0.0; --i) {
      ulong ticket = PositionGetTicket(i);
      if(!PositionSelectByTicket(ticket)) continue;
      if(PositionGetString(POSITION_SYMBOL) != realSym) continue;
      
      ENUM_POSITION_TYPE typ = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      double posVol = PositionGetDouble(POSITION_VOLUME);
      double lotsToClose = MathMin(posVol, remaining);
      
      double price = (typ == POSITION_TYPE_BUY)
                     ? SymbolInfoDouble(realSym, SYMBOL_BID)
                     : SymbolInfoDouble(realSym, SYMBOL_ASK);
      
      MqlTradeRequest req;
      ZeroMemory(req);
      MqlTradeResult res;
      ZeroMemory(res);
      
      req.action = TRADE_ACTION_DEAL;
      req.symbol = realSym;
      req.volume = lotsToClose;
      req.price = price;
      req.deviation = Slippage;
      req.magic = (MagicNumberInput > 0 ? MagicNumberInput : ComputeAutoMagic());
      req.type_filling = ORDER_FILLING_FOK;
      req.position = (ulong)ticket;
      req.type = (typ == POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
      
      ResetLastError();
      if(OrderSend(req, res)) {
         any = true;
         remaining -= lotsToClose;
         LogMessage(LOG_INFO, "[" + IntegerToString(process_id) + "] Closed " + DoubleToString(lotsToClose, 2) + " lots, remain " + DoubleToString(remaining, 2));
      } else {
         LogMessage(LOG_ERROR, "[" + IntegerToString(process_id) + "] Close failed: ret=" + IntegerToString(res.retcode) + " err=" + IntegerToString(GetLastError()));
      }
   }
   
   return any;
}

bool CloseAllPositionsBySymbol(string sym, string source = "SLAVE") {
   string realSym = ResolveSymbol(sym);
   if(realSym == "") {
      LogMessage(LOG_ERROR, "[CLOSE_ALL] Cannot resolve symbol: " + sym);
      return false;
   }
   double total = 0.0;
   for(int i = PositionsTotal() - 1; i >= 0; --i) {
      ulong t = PositionGetTicket(i);
      if(!PositionSelectByTicket(t)) continue;
      if(PositionGetString(POSITION_SYMBOL) != realSym) continue;
      total += PositionGetDouble(POSITION_VOLUME);
   }
   if(total <= 0.0) return false;
   return ClosePositionsByAmount(sym, total, source);
}

bool ClosePositionByTicket(ulong ticket, string source = "SLAVE") {
   if(!PositionSelectByTicket(ticket)) {
      LogMessage(LOG_WARNING, "[CLOSE_TICKET] Position not found: " + IntegerToString((int)ticket));
      return false;
   }
   string sym = PositionGetString(POSITION_SYMBOL);
   int typ = (int)PositionGetInteger(POSITION_TYPE);
   double vol = PositionGetDouble(POSITION_VOLUME);
   double price = (typ == POSITION_TYPE_BUY) ? SymbolInfoDouble(sym, SYMBOL_BID) : SymbolInfoDouble(sym, SYMBOL_ASK);

   MqlTradeRequest req; MqlTradeResult res;
   ZeroMemory(req); ZeroMemory(res);

   req.action   = TRADE_ACTION_DEAL;
   req.position = ticket;
   req.symbol   = sym;
   req.volume   = vol;
   req.price    = price;
   req.deviation= Slippage;
   req.magic    = (MagicNumberInput > 0 ? MagicNumberInput : ComputeAutoMagic());
   req.type     = (typ == POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
   req.type_filling = ORDER_FILLING_FOK;

   ResetLastError();
   bool ok = OrderSend(req, res);
   if(ok) {
      LogMessage(LOG_INFO, "[CLOSE_TICKET] Closed ticket " + IntegerToString((int)ticket) + " vol=" + DoubleToString(vol,2));
   } else {
      LogMessage(LOG_ERROR, "[CLOSE_TICKET] Failed ticket " + IntegerToString((int)ticket) + " ret=" + IntegerToString((int)res.retcode) + " err=" + IntegerToString(GetLastError()));
   }
   return ok;
}

bool CloseOppositePositionsBySymbol(string sym, string incoming_action, string source = "WEBHOOK") {
   string realSym = ResolveSymbol(sym);
   if(realSym == "") {
      LogMessage(LOG_ERROR, "[CLOSE_OPP] Cannot resolve symbol: " + sym);
      return false;
   }
   string act = ToLower(incoming_action);
   int targetType = -1;
   if(act == "buy")  targetType = POSITION_TYPE_SELL;
   if(act == "sell") targetType = POSITION_TYPE_BUY;
   if(targetType < 0) return false;

   ulong toClose[];
   for(int i = 0; i < PositionsTotal(); ++i) {
      ulong t = PositionGetTicket(i);
      if(!PositionSelectByTicket(t)) continue;
      if(PositionGetString(POSITION_SYMBOL) != realSym) continue;
      int typ = (int)PositionGetInteger(POSITION_TYPE);
      if(typ == targetType) {
         int n = ArraySize(toClose);
         ArrayResize(toClose, n+1);
         toClose[n] = t;
      }
   }
   bool any = false;
   for(int i = 0; i < ArraySize(toClose); ++i) {
      any |= ClosePositionByTicket(toClose[i], source);
   }
   return any;
}

int CollectSymbolTickets(string sym, ulong &tickets[]) {
   ArrayResize(tickets, 0);
   string realSym = ResolveSymbol(sym);
   if(realSym == "") return 0;
   
   for(int i = 0; i < PositionsTotal(); ++i) {
      ulong t = PositionGetTicket(i);
      if(!PositionSelectByTicket(t)) continue;
      if(PositionGetString(POSITION_SYMBOL) != realSym) continue;
      int n = ArraySize(tickets);
      ArrayResize(tickets, n+1);
      tickets[n] = t;
   }
   
   int n = ArraySize(tickets);
   for(int i = 0; i < n; ++i) {
      for(int j = i+1; j < n; ++j) {
         datetime ti = 0, tj = 0;
         if(PositionSelectByTicket(tickets[i])) ti = (datetime)PositionGetInteger(POSITION_TIME);
         if(PositionSelectByTicket(tickets[j])) tj = (datetime)PositionGetInteger(POSITION_TIME);
         if(tj < ti) {
            ulong tmp = tickets[i];
            tickets[i] = tickets[j];
            tickets[j] = tmp;
         }
      }
   }
   return n;
}

bool ClosePositionByIndex(string sym, int index1based, string source = "SLAVE") {
   ulong tickets[];
   int n = CollectSymbolTickets(sym, tickets);
   if(n <= 0) return false;
   int idx = index1based - 1;
   if(idx < 0 || idx >= n) {
      LogMessage(LOG_WARNING, "[CLOSE_INDEX] Index out of range: " + IntegerToString(index1based) + " of " + IntegerToString(n));
      return false;
   }
   return ClosePositionByTicket(tickets[idx], source);
}

bool ModifyPositionByTicket(ulong ticket, double sl, double tp) {
   if(!PositionSelectByTicket(ticket)) {
      LogMessage(LOG_WARNING, "[MODIFY_TICKET] Position not found: " + IntegerToString((int)ticket));
      return false;
   }
   string sym = PositionGetString(POSITION_SYMBOL);
   int digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
   double sln = (sl > 0 ? NormalizeDouble(sl, digits) : 0.0);
   double tpn = (tp > 0 ? NormalizeDouble(tp, digits) : 0.0);

   MqlTradeRequest req; MqlTradeResult res;
   ZeroMemory(req); ZeroMemory(res);

   req.action   = TRADE_ACTION_SLTP;
   req.position = ticket;
   req.symbol   = sym;
   req.sl       = sln;
   req.tp       = tpn;
   req.magic    = (MagicNumberInput > 0 ? MagicNumberInput : ComputeAutoMagic());

   ResetLastError();
   bool ok = OrderSend(req, res);
   if(ok) {
      LogMessage(LOG_INFO, "[MODIFY_TICKET] Modified ticket " + IntegerToString((int)ticket) + " SL=" + DoubleToString(sln, digits) + " TP=" + DoubleToString(tpn, digits));
   } else {
      LogMessage(LOG_ERROR, "[MODIFY_TICKET] Failed modify ticket " + IntegerToString((int)ticket) + " ret=" + IntegerToString((int)res.retcode) + " err=" + IntegerToString(GetLastError()));
   }
   return ok;
}

bool ModifyPositionsBySymbol(string sym, double sl, double tp) {
   string realSym = ResolveSymbol(sym);
   if(realSym == "") {
      LogMessage(LOG_ERROR, "[MODIFY_ALL] Cannot resolve symbol: " + sym);
      return false;
   }
   bool any = false;
   for(int i = 0; i < PositionsTotal(); ++i) {
      ulong t = PositionGetTicket(i);
      if(!PositionSelectByTicket(t)) continue;
      if(PositionGetString(POSITION_SYMBOL) != realSym) continue;
      any |= ModifyPositionByTicket(t, sl, tp);
   }
   return any;
}

bool ModifyPositionByIndex(string sym, int index1based, double sl, double tp) {
   ulong tickets[];
   int n = CollectSymbolTickets(sym, tickets);
   if(n <= 0) return false;
   int idx = index1based - 1;
   if(idx < 0 || idx >= n) {
      LogMessage(LOG_WARNING, "[MODIFY_INDEX] Index out of range: " + IntegerToString(index1based) + " of " + IntegerToString(n));
      return false;
   }
   return ModifyPositionByTicket(tickets[idx], sl, tp);
}

bool ClosePositionByExactComment(string targetComment, string source = "SLAVE") {
   if(targetComment == "") return false;
   for(int i = PositionsTotal() - 1; i >= 0; --i) {
      ulong t = PositionGetTicket(i);
      if(!PositionSelectByTicket(t)) continue;
      string c = PositionGetString(POSITION_COMMENT);
      if(c == targetComment) {
         return ClosePositionByTicket(t, source);
      }
   }
   LogMessage(LOG_WARNING, "[CLOSE_COMMENT] Not found comment: " + targetComment);
   return false;
}

bool ModifyPositionByExactComment(string targetComment, double sl, double tp) {
   if(targetComment == "") return false;
   for(int i = 0; i < PositionsTotal(); ++i) {
     ulong t = PositionGetTicket(i);
     if(!PositionSelectByTicket(t)) continue;
     string c = PositionGetString(POSITION_COMMENT);
     if(c == targetComment) {
        return ModifyPositionByTicket(t, sl, tp);
     }
   }
   LogMessage(LOG_WARNING, "[MODIFY_COMMENT] Not found comment: " + targetComment);
   return false;
}

//==================== File I/O (Thread-Safe) ====================
bool ReadAllText(const string path, string &out) {
   int h = FileOpen(path, FILE_READ | FILE_BIN);
   if(h == INVALID_HANDLE) return false;
   
   int sz = (int)FileSize(h);
   if(sz == 0) {
      FileClose(h);
      out = "";
      return true;
   }
   
   char data[];
   ArrayResize(data, sz);
   int n = FileReadArray(h, data, 0, sz);
   FileClose(h);
   
   if(n <= 0) {
      out = "";
      return true;
   }
   
   int start = 0;
   if(n >= 3 && (uchar)data[0] == 0xEF && (uchar)data[1] == 0xBB && (uchar)data[2] == 0xBF)
      start = 3;
   
   out = CharArrayToString(data, start, n - start);
   return true;
}

void CleanupFile(const string full, bool delete_flag) {
   if(delete_flag) FileDelete(full);
}

//==================== Webhook Mode ====================
bool ProcessWebhookFile(const string base, const string pattern, bool delete_flag) {
   string mask = (base == "" ? pattern : base + "\\" + pattern);
   string found = "";
   bool processed_any = false;
   long h = FileFindFirst(mask, found, 0);
   if(h == INVALID_HANDLE) return false;
   do {
      if(found == "") break;
      string full = (base == "" ? found : base + "\\" + found);
      string js;
      if(!ReadAllText(full, js)) {
         LogMessage(LOG_ERROR, "[WEBHOOK] Cannot read " + full);
      } else {
         string sym = GetVal(js, "broker_symbol");
         if(sym == "") sym = GetVal(js, "symbol");
         if(sym == "") sym = GetVal(js, "original_symbol");

         string action = ToLower(GetVal(js, "action"));
         if(action == "long") action = "buy";
         if(action == "short") action = "sell";

         string otype = ToLower(GetVal(js, "order_type"));
         string comment = GetVal(js, "comment");
         double vol = StringToDouble(GetVal(js, "volume"));
         if(vol <= 0) vol = DefaultVolume;

         string tp_s = GetVal(js, "tp");
         if(tp_s == "") tp_s = GetVal(js, "take_profit");
         string sl_s = GetVal(js, "sl");
         if(sl_s == "") sl_s = GetVal(js, "stop_loss");
         double tp = StringToDouble(tp_s);
         double sl = StringToDouble(sl_s);
         double price = StringToDouble(GetVal(js, "price"));
         string exp = GetVal(js, "expire");

         string cmdtype = ToLower(GetVal(js, "command_type"));
         string close_by = ToLower(GetVal(js, "close_by"));
         string index_s = GetVal(js, "index");
         string ticket_s = GetVal(js, "ticket");
         if(ticket_s == "") ticket_s = GetVal(js, "position_ticket");

         if(action == "close_symbol") {
            CloseAllPositionsBySymbol(sym, "WEBHOOK");
            CleanupFile(full, delete_flag);
            processed_any = true;
            continue;
         } else if(action == "close" || cmdtype == "close_position") {
            // 1. ปิดด้วย Comment (ถ้ามี)
            if(comment != "") {
               ClosePositionByExactComment(comment, "WEBHOOK");
               CleanupFile(full, delete_flag);
               processed_any = true;
               continue;
            }
            
            // 2. ✅ FIX: ปิดด้วย Ticket (เช็คว่า ticket > 0)
            if(ticket_s != "") {
               ulong tk = (ulong)StringToInteger(ticket_s);
               if(tk > 0) {
                  ClosePositionByTicket(tk, "WEBHOOK");
                  CleanupFile(full, delete_flag);
                  processed_any = true;
                  continue;
               } else {
                  LogMessage(LOG_WARNING, "[WEBHOOK] ticket=0, trying fallback methods");
               }
            }
            
            // 3. ปิดด้วย Index
            int idx = (index_s != "" ? (int)StringToInteger(index_s) : 0);
            if(idx > 0) {
               ClosePositionByIndex(sym, idx, "WEBHOOK");
               CleanupFile(full, delete_flag);
               processed_any = true;
               continue;
            }
            
            // 4. ✅ FIX: Fallback - ปิดด้วย Volume หรือ Symbol
            double reqVol = StringToDouble(GetVal(js, "volume"));
            if(reqVol > 0) {
               ClosePositionsByAmount(sym, reqVol, "WEBHOOK");
            } else if(sym != "") {
               CloseAllPositionsBySymbol(sym, "WEBHOOK");
            } else {
               LogMessage(LOG_ERROR, "[WEBHOOK] Cannot close: no valid ticket/index/symbol/volume");
            }
            CleanupFile(full, delete_flag);
            processed_any = true;
            continue;
         }

         if(action == "modify" || cmdtype == "modify_position") {
            double newTP = StringToDouble(GetVal(js, "tp"));
            if(newTP == 0) newTP = StringToDouble(GetVal(js, "take_profit"));
            double newSL = StringToDouble(GetVal(js, "sl"));
            if(newSL == 0) newSL = StringToDouble(GetVal(js, "stop_loss"));

            if(comment != "") {
               ModifyPositionByExactComment(comment, newSL, newTP);
               CleanupFile(full, delete_flag);
               processed_any = true;
               continue;
            }
            if(ticket_s != "") {
               ulong tk2 = (ulong)StringToInteger(ticket_s);
               ModifyPositionByTicket(tk2, newSL, newTP);
               CleanupFile(full, delete_flag);
               processed_any = true;
               continue;
            }
            int idxm = (index_s != "" ? (int)StringToInteger(index_s) : 0);
            if(idxm > 0) {
               ModifyPositionByIndex(sym, idxm, newSL, newTP);
               CleanupFile(full, delete_flag);
               processed_any = true;
               continue;
            }
            ModifyPositionsBySymbol(sym, newSL, newTP);
            CleanupFile(full, delete_flag);
            processed_any = true;
            continue;
         }

         if(action != "buy" && action != "sell") {
            LogMessage(LOG_WARNING, "[WEBHOOK] Unknown action: " + action);
            CleanupFile(full, delete_flag);
            processed_any = true;
            continue;
         }
         SendOrderAdvanced(action, otype, sym, vol, price, sl, tp, comment, exp, "WEBHOOK");
         CleanupFile(full, delete_flag);
         processed_any = true;
         continue;
      }
   } while(FileFindNext(h, found));
   FileFindClose(h);
   return processed_any;
}

void ProcessWebhookMode() {
   if(!g_webhook_readyFB) return;
   if(g_webhook_instanceSub != "" && ProcessWebhookFile(g_webhook_instanceSub, Webhook_FilePattern, Webhook_DeleteAfterProcess)) return;
   ProcessWebhookFile("", Webhook_FilePattern, Webhook_DeleteAfterProcess);
}

//==================== Slave Mode ====================
bool ProcessSlaveFile(const string base, const string pattern, bool delete_flag) {
   string mask = (base == "" ? pattern : base + "\\" + pattern);
   string found = "";
   bool processed_any = false;
   long h = FileFindFirst(mask, found, 0);
   if(h == INVALID_HANDLE) return false;
   do {
      if(found == "") break;
      string full = (base == "" ? found : base + "\\" + found);
      string js;
      if(!ReadAllText(full, js)) {
         LogMessage(LOG_ERROR, "[SLAVE] Cannot read " + full);
      } else {
         string sym = GetVal(js, "broker_symbol");
         if(sym == "") sym = GetVal(js, "symbol");
         if(sym == "") sym = GetVal(js, "original_symbol");

         string action = ToLower(GetVal(js, "action"));
         if(action == "long") action = "buy";
         if(action == "short") action = "sell";

         string otype = ToLower(GetVal(js, "order_type"));
         string comment = GetVal(js, "comment");
         double vol = StringToDouble(GetVal(js, "volume"));
         if(vol <= 0) vol = DefaultVolume;

         string tp_s = GetVal(js, "tp");
         if(tp_s == "") tp_s = GetVal(js, "take_profit");
         string sl_s = GetVal(js, "sl");
         if(sl_s == "") sl_s = GetVal(js, "stop_loss");
         double tp = StringToDouble(tp_s);
         double sl = StringToDouble(sl_s);
         double price = StringToDouble(GetVal(js, "price"));
         string exp = GetVal(js, "expire");

         string cmdtype = ToLower(GetVal(js, "command_type"));
         string close_by = ToLower(GetVal(js, "close_by"));
         string index_s = GetVal(js, "index");
         string ticket_s = GetVal(js, "ticket");
         if(ticket_s == "") ticket_s = GetVal(js, "position_ticket");

         if(action == "close_symbol") {
            CloseAllPositionsBySymbol(sym, "SLAVE");
            CleanupFile(full, delete_flag);
            processed_any = true;
            continue;
         } else if(action == "close" || cmdtype == "close_position") {
            // 1. ปิดด้วย Comment (ถ้ามี)
            if(comment != "") {
               ClosePositionByExactComment(comment, "SLAVE");
               CleanupFile(full, delete_flag);
               processed_any = true;
               continue;
            }
            
            // 2. ✅ FIX: ปิดด้วย Ticket (เช็คว่า ticket > 0)
            if(ticket_s != "") {
               ulong tk = (ulong)StringToInteger(ticket_s);
               if(tk > 0) {
                  ClosePositionByTicket(tk, "SLAVE");
                  CleanupFile(full, delete_flag);
                  processed_any = true;
                  continue;
               } else {
                  LogMessage(LOG_WARNING, "[SLAVE] ticket=0, trying fallback methods");
               }
            }
            
            // 3. ปิดด้วย Index
            int idx = (index_s != "" ? (int)StringToInteger(index_s) : 0);
            if(idx > 0) {
               ClosePositionByIndex(sym, idx, "SLAVE");
               CleanupFile(full, delete_flag);
               processed_any = true;
               continue;
            }
            
            // 4. ✅ FIX: Fallback - ปิดด้วย Volume หรือ Symbol
            double reqVol = StringToDouble(GetVal(js, "volume"));
            if(reqVol > 0) {
               ClosePositionsByAmount(sym, reqVol, "SLAVE");
            } else if(sym != "") {
               CloseAllPositionsBySymbol(sym, "SLAVE");
            } else {
               LogMessage(LOG_ERROR, "[SLAVE] Cannot close: no valid ticket/index/symbol/volume");
            }
            CleanupFile(full, delete_flag);
            processed_any = true;
            continue;
         }

         if(action == "modify" || cmdtype == "modify_position") {
            double newTP = StringToDouble(GetVal(js, "tp"));
            if(newTP == 0) newTP = StringToDouble(GetVal(js, "take_profit"));
            double newSL = StringToDouble(GetVal(js, "sl"));
            if(newSL == 0) newSL = StringToDouble(GetVal(js, "stop_loss"));

            if(comment != "") {
               ModifyPositionByExactComment(comment, newSL, newTP);
               CleanupFile(full, delete_flag);
               processed_any = true;
               continue;
            }
            if(ticket_s != "") {
               ulong tk2 = (ulong)StringToInteger(ticket_s);
               ModifyPositionByTicket(tk2, newSL, newTP);
               CleanupFile(full, delete_flag);
               processed_any = true;
               continue;
            }
            int idxm = (index_s != "" ? (int)StringToInteger(index_s) : 0);
            if(idxm > 0) {
               ModifyPositionByIndex(sym, idxm, newSL, newTP);
               CleanupFile(full, delete_flag);
               processed_any = true;
               continue;
            }
            ModifyPositionsBySymbol(sym, newSL, newTP);
            CleanupFile(full, delete_flag);
            processed_any = true;
            continue;
         }

         if(action != "buy" && action != "sell") {
            LogMessage(LOG_WARNING, "[SLAVE] Unknown action: " + action);
            CleanupFile(full, delete_flag);
            processed_any = true;
            continue;
         }
         SendOrderAdvanced(action, otype, sym, vol, price, sl, tp, comment, exp, "SLAVE");
         CleanupFile(full, delete_flag);
         processed_any = true;
         continue;
      }
   } while(FileFindNext(h, found));
   FileFindClose(h);
   return processed_any;
}

void ProcessSlaveMode() {
   if(!g_slave_readyFB) return;
   if(g_slave_instanceSub != "" && ProcessSlaveFile(g_slave_instanceSub, Slave_FilePattern, Slave_DeleteAfterProcess)) return;
   ProcessSlaveFile("", Slave_FilePattern, Slave_DeleteAfterProcess);
}

//==================== Master Mode ====================
void InitMasterPositions() {
   int total = PositionsTotal();
   
   ArrayResize(MasterTickets, total);
   ArrayResize(MasterSymbols, total);
   ArrayResize(MasterTypes, total);
   ArrayResize(MasterVolumes, total);
   ArrayResize(MasterTPs, total);
   ArrayResize(MasterSLs, total);
   
   for(int i = 0; i < total; i++) {
      ulong ticket = PositionGetTicket(i);
      if(ticket > 0) {
         MasterTickets[i] = ticket;
         MasterSymbols[i] = PositionGetString(POSITION_SYMBOL);
         MasterTypes[i] = (int)PositionGetInteger(POSITION_TYPE);
         MasterVolumes[i] = PositionGetDouble(POSITION_VOLUME);
         MasterTPs[i] = PositionGetDouble(POSITION_TP);
         MasterSLs[i] = PositionGetDouble(POSITION_SL);
      }
   }
   
   LogMessage(LOG_INFO, "[MASTER] Initialized " + IntegerToString(total) + " existing positions");
}

void SendSignal(string event, string symbol, int type, double volume, double tp, double sl, ulong master_ticket) {
   string url = Master_ServerURL + "/api/copy/trade";

   string typeStr = (type == POSITION_TYPE_BUY) ? "BUY" : "SELL";
   string order_id = "order_" + IntegerToString((int)master_ticket);

   string json = "{";
   json += "\"api_key\":\"" + Master_APIKey + "\",";
   json += "\"account\":\"" + AccountNumber + "\",";
   json += "\"event\":\"" + event + "\",";
   json += "\"type\":\"" + typeStr + "\",";
   json += "\"symbol\":\"" + symbol + "\",";
   json += "\"volume\":" + DoubleToString(volume, 2);
   json += ",\"order_id\":\"" + order_id + "\"";

   if(tp > 0) json += ",\"tp\":" + DoubleToString(tp, _Digits);
   if(sl > 0) json += ",\"sl\":" + DoubleToString(sl, _Digits);

   json += "}";

   char postData[];
   char resultData[];
   string headers = "Content-Type: application/json\r\n";

   StringToCharArray(json, postData, 0, StringLen(json));

   int timeout = Master_HttpTimeoutMs;
   int result = WebRequest("POST", url, headers, timeout, postData, resultData, headers);

   if(result == 200) {
      string response = CharArrayToString(resultData);
      LogMessage(LOG_INFO, "[MASTER] Signal sent: " + event + " " + typeStr + " " + symbol + " " + DoubleToString(volume, 2) + " | Order ID: " + order_id);
      LogMessage(LOG_DEBUG, "Response: " + response);
   } else if(result == -1) {
      int error = GetLastError();
      LogMessage(LOG_ERROR, "[MASTER] WebRequest failed: Error " + IntegerToString(error) + " - Add '" + Master_ServerURL + "' to allowed URLs");
   } else {
      string response = CharArrayToString(resultData);
      LogMessage(LOG_ERROR, "[MASTER] Signal failed: HTTP " + IntegerToString(result) + " - " + response);
   }
}

void CheckMasterPositions() {
   int currentTotal = PositionsTotal();
   int previousTotal = ArraySize(MasterTickets);

   for(int i = 0; i < currentTotal; i++) {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;

      bool isNew = true;
      int posIndex = -1;

      for(int j = 0; j < previousTotal; j++) {
         if(MasterTickets[j] == ticket) {
            isNew = false;
            posIndex = j;
            break;
         }
      }

      if(isNew && Master_SendOnOpen) {
         string symbol = PositionGetString(POSITION_SYMBOL);
         int type = (int)PositionGetInteger(POSITION_TYPE);
         double volume = PositionGetDouble(POSITION_VOLUME);
         double tp = PositionGetDouble(POSITION_TP);
         double sl = PositionGetDouble(POSITION_SL);

         SendSignal("deal_add", symbol, type, volume, tp, sl, ticket);

         ArrayResize(MasterTickets, previousTotal + 1);
         ArrayResize(MasterSymbols, previousTotal + 1);
         ArrayResize(MasterTypes, previousTotal + 1);
         ArrayResize(MasterVolumes, previousTotal + 1);
         ArrayResize(MasterTPs, previousTotal + 1);
         ArrayResize(MasterSLs, previousTotal + 1);

         MasterTickets[previousTotal] = ticket;
         MasterSymbols[previousTotal] = symbol;
         MasterTypes[previousTotal] = type;
         MasterVolumes[previousTotal] = volume;
         MasterTPs[previousTotal] = tp;
         MasterSLs[previousTotal] = sl;

         previousTotal++;
      } 
      else if(!isNew && posIndex >= 0) {
         double currentTP = PositionGetDouble(POSITION_TP);
         double currentSL = PositionGetDouble(POSITION_SL);

         if(Master_SendOnModify &&
            (MasterTPs[posIndex] != currentTP || MasterSLs[posIndex] != currentSL)) {
            string symbol = PositionGetString(POSITION_SYMBOL);
            int type = (int)PositionGetInteger(POSITION_TYPE);
            double volume = PositionGetDouble(POSITION_VOLUME);

            SendSignal("position_modify", symbol, type, volume, currentTP, currentSL, ticket);

            MasterTPs[posIndex] = currentTP;
            MasterSLs[posIndex] = currentSL;
         }
      }
   }

   if(Master_SendOnClose && currentTotal < previousTotal) {
      for(int i = 0; i < previousTotal; i++) {
         ulong oldTicket = MasterTickets[i];
         bool stillExists = false;

         for(int j = 0; j < currentTotal; j++) {
            if(PositionGetTicket(j) == oldTicket) {
               stillExists = true;
               break;
            }
         }

         if(!stillExists) {
            SendSignal("deal_close", MasterSymbols[i], MasterTypes[i], MasterVolumes[i], 0, 0, oldTicket);
         }
      }

      ulong tempTickets[];
      string tempSymbols[];
      int tempTypes[];
      double tempVolumes[];
      double tempTPs[];
      double tempSLs[];

      int newSize = 0;
      for(int i = 0; i < currentTotal; i++) {
         ulong ticket = PositionGetTicket(i);
         if(ticket > 0) {
            ArrayResize(tempTickets, newSize + 1);
            ArrayResize(tempSymbols, newSize + 1);
            ArrayResize(tempTypes, newSize + 1);
            ArrayResize(tempVolumes, newSize + 1);
            ArrayResize(tempTPs, newSize + 1);
            ArrayResize(tempSLs, newSize + 1);

            tempTickets[newSize] = ticket;
            tempSymbols[newSize] = PositionGetString(POSITION_SYMBOL);
            tempTypes[newSize] = (int)PositionGetInteger(POSITION_TYPE);
            tempVolumes[newSize] = PositionGetDouble(POSITION_VOLUME);
            tempTPs[newSize] = PositionGetDouble(POSITION_TP);
            tempSLs[newSize] = PositionGetDouble(POSITION_SL);
            newSize++;
         }
      }

      ArrayResize(MasterTickets, newSize);
      ArrayResize(MasterSymbols, newSize);
      ArrayResize(MasterTypes, newSize);
      ArrayResize(MasterVolumes, newSize);
      ArrayResize(MasterTPs, newSize);
      ArrayResize(MasterSLs, newSize);

      if(newSize > 0) {
         ArrayCopy(MasterTickets, tempTickets);
         ArrayCopy(MasterSymbols, tempSymbols);
         ArrayCopy(MasterTypes, tempTypes);
         ArrayCopy(MasterVolumes, tempVolumes);
         ArrayCopy(MasterTPs, tempTPs);
         ArrayCopy(MasterSLs, tempSLs);
      }
   }
}

//==================== File Bridge Setup ====================
bool SetupFileBridge(string instanceRootPath, bool autoLink, string &instanceSub, bool &readyFB, bool &directMode, string mode_name) {
   int acc = (int)AccountInfoInteger(ACCOUNT_LOGIN);
   string accStr = IntegerToString(acc);
   
   string src = instanceRootPath + "\\" + accStr + "\\MQL5\\Files";
   string df = TerminalInfoString(TERMINAL_DATA_PATH);
   string fr = FilesRoot();
   string dst = df + "\\MQL5\\Files\\instance_" + accStr;
   
   directMode = (NormalizePath(src) == NormalizePath(fr));
   
   if(directMode) {
      instanceSub = "";
      readyFB = true;
      LogMessage(LOG_INFO, "[" + mode_name + "] DIRECT MODE: Reading from MQL5\\Files (root)");
   } else {
      instanceSub = "instance_" + accStr;
      
      LogMessage(LOG_INFO, "[" + mode_name + "] Instance Mode:");
      LogMessage(LOG_INFO, "   DataFolder: " + df);
      LogMessage(LOG_INFO, "   Source:     " + src);
      LogMessage(LOG_INFO, "   Dest:       " + dst);
      
      if(autoLink) {
         if(!FolderExistsUnderFiles(instanceSub)) {
            LogMessage(LOG_INFO, "[" + mode_name + "] Creating junction...");
            CreateJunction(dst, src);
         } else {
            LogMessage(LOG_INFO, "[" + mode_name + "] Junction exists: " + instanceSub);
         }
      }
      
      readyFB = FolderExistsUnderFiles(instanceSub);
      if(!readyFB) {
         LogMessage(LOG_WARNING, "[" + mode_name + "] FileBridge not ready. Folder missing: " + instanceSub);
      } else {
         LogMessage(LOG_INFO, "[" + mode_name + "] FileBridge ready");
      }
   }
   
   return readyFB;
}

//==================== Logging ====================
void LogMessage(ENUM_LOG_LEVEL level, string message) {
   if(!EnableLogging) return;
   if(level < LogLevel) return;
   
   string prefix = "";
   switch(level) {
      case LOG_DEBUG:   prefix = "[DEBUG] "; break;
      case LOG_INFO:    prefix = "[INFO] "; break;
      case LOG_WARNING: prefix = "[WARN] "; break;
      case LOG_ERROR:   prefix = "[ERROR] "; break;
   }
   
   string fullMessage = prefix + TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS) + " " + message;
   Print(fullMessage);
   
   string filename = "AllInOneEA_" + AccountNumber + ".log";
   int handle = FileOpen(filename, FILE_WRITE | FILE_READ | FILE_TXT | FILE_ANSI);
   
   if(handle != INVALID_HANDLE) {
      FileSeek(handle, 0, SEEK_END);
      FileWriteString(handle, fullMessage + "\n");
      FileClose(handle);
   }
}

//==================== EA Lifecycle ====================
int OnInit() {
   AccountNumber = IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN));
   g_magic = (MagicNumberInput > 0 ? MagicNumberInput : ComputeAutoMagic());
   
   LogMessage(LOG_INFO, "=== All-in-One Trading EA v2.01 Started ===");
   LogMessage(LOG_INFO, "Account: " + AccountNumber);
   LogMessage(LOG_INFO, "Magic: " + IntegerToString(g_magic));
   
   if(!EnableWebhook && !EnableMaster && !EnableSlave) {
      Alert("⚠️ Please enable at least one mode!");
      LogMessage(LOG_ERROR, "No mode enabled");
      return(INIT_PARAMETERS_INCORRECT);
   }
   
   string modes = "";
   if(EnableWebhook) modes += "WEBHOOK ";
   if(EnableMaster) modes += "MASTER ";
   if(EnableSlave) modes += "SLAVE ";
   LogMessage(LOG_INFO, "Enabled Modes: " + modes);
   
   if(EnableWebhook) {
      LogMessage(LOG_INFO, "=== Initializing Webhook Mode ===");
      SetupFileBridge(Webhook_InstanceRootPath, Webhook_AutoLinkInstance, 
                     g_webhook_instanceSub, g_webhook_readyFB, g_webhook_directMode, "WEBHOOK");
      LogMessage(LOG_INFO, "Webhook polling: " + IntegerToString(Webhook_PollingSeconds) + " seconds");
      LogMessage(LOG_INFO, "Webhook pattern: " + Webhook_FilePattern);
   }
   
   if(EnableMaster) {
      LogMessage(LOG_INFO, "=== Initializing Master Mode ===");
      
      if(Master_APIKey == "") {
         Alert("⚠️ Master Mode requires API Key!");
         LogMessage(LOG_ERROR, "Master Mode requires API Key");
         return(INIT_PARAMETERS_INCORRECT);
      }
      
      if(Master_ServerURL == "") {
         Alert("⚠️ Server URL is required!");
         LogMessage(LOG_ERROR, "Server URL is required");
         return(INIT_PARAMETERS_INCORRECT);
      }
      
      LogMessage(LOG_INFO, "Master API Key: " + StringSubstr(Master_APIKey, 0, 8) + "...");
      LogMessage(LOG_INFO, "Master Server: " + Master_ServerURL);
      InitMasterPositions();
   }
   
   if(EnableSlave) {
      LogMessage(LOG_INFO, "=== Initializing Slave Mode ===");
      SetupFileBridge(Slave_InstanceRootPath, Slave_AutoLinkInstance,
                     g_slave_instanceSub, g_slave_readyFB, g_slave_directMode, "SLAVE");
      LogMessage(LOG_INFO, "Slave polling: " + IntegerToString(Slave_PollingSeconds) + " seconds");
      LogMessage(LOG_INFO, "Slave pattern: " + Slave_FilePattern);
   }
   
   Initialized = true;
   
   int timer_seconds = 999;
   if(EnableWebhook) timer_seconds = MathMin(timer_seconds, Webhook_PollingSeconds);
   if(EnableSlave) timer_seconds = MathMin(timer_seconds, Slave_PollingSeconds);
   if(timer_seconds == 999) timer_seconds = 1;
   
   EventSetTimer(MathMax(1, timer_seconds));
   
   LogMessage(LOG_INFO, "✅ Initialization complete");
   LogMessage(LOG_INFO, "Timer interval: " + IntegerToString(timer_seconds) + " seconds");
   
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason) {
   EventKillTimer();
   LogMessage(LOG_INFO, "EA Stopped");
}

void OnTimer() {
   if(!Initialized) return;
   
   if(EnableWebhook) {
      ProcessWebhookMode();
   }
   
   if(EnableMaster) {
      CheckMasterPositions();
   }
   
   if(EnableSlave) {
      ProcessSlaveMode();
   }
}

void OnTradeTransaction(const MqlTradeTransaction& trans,
                       const MqlTradeRequest& request,
                       const MqlTradeResult& result)
{
   if(!EnableMaster) return;
   if(!Initialized) return;
   
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD) {
      Sleep(100);
      CheckMasterPositions();
   }
}
//+------------------------------------------------------------------+
