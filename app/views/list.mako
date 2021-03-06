# -*- coding: utf-8 -*-
<%namespace name="base" module="app.helpers.base"/>\
<%namespace name="helper" module="app.helpers.list"/>\
<%inherit file="layout.mako" />

<div id="doc3">    

  <div id="hd">

    <h1>      
      %for i in range(len(path_components)):
        <a href="/${'/'.join(path_components[0:i+1])}/">${path_names[i]}</a> <span>/</span>
      %endfor
    </h1>
    
    <p class="rss rss-top"><a href="/${path}/?format=rss"><img src="/shrub/images/rss.png" alt="RSS"/></a></p>
  </div>  
  
  <div id="bd">

    <div id="yui-main">
    
      <div class="yui-b">
      
        %if s3response.is_truncated:
          <hr/>
          <p><a href="${next_page_url}">Next page</a>
          &mdash;
          <span class="info">The response was truncated (max-keys=${s3response.data.max_keys}).</span>
          </p>
          <hr/>          
        %endif
        
        %if warning_message:
        <p><span class="warn">${warning_message}</span></p>
        <hr/>
        %endif
        
        %if len(s3response.files) == 0:
          <hr/>
          <p class="warn"><span>No files available.</span></p>            
        %else:
        
        <table class="s3">            
        <colgroup>
          <col width="70%"/>
          <col width="20%"/>
          <col width="10%"/>
        </colgroup>
        <thead>
          <tr>
          ${helper.header_link('Name', 'name', sort, sort_asc, path)}
          ${helper.header_link('Date', 'date', sort, sort_asc, path)}
          ${helper.header_link('Size', 'size', sort, sort_asc, path)}
          </tr>
        </thead>
        <tbody>
        %for i in range(len(s3response.files)):
        <% file = s3response.files[i] %>
        <tr class="${helper.if_even(i, 'even', 'odd')}">
          <td>
            %if file.is_folder:
              <img src="/shrub/images/folder.png"/>
              <a class="name folder" href="/${file.name_with_prefix(path, False)}">${file.name | h}</a>              
            %else:
              <img src="/shrub/images/page_white.png"/>
              <a class="name file" href="${file.url}">${file.name | h}</a>
            %endif
          </td>
          <td class="date">${file.pretty_last_modified('-')}</td>
          <td class="size">${file.pretty_size('-')}</td>
        </tr>
        %endfor
        </tbody>
        </table>
        
        %endif
      
      </div>
    
    </div>
  </div>
  
  <div id="ft">    
    <p>
      Formats: 
        <a href="/${path}/?format=rss">RSS</a> /
        <a href="/${path}/?format=json">JSON</a> /
        <a href="/${path}/?format=xspf">XSPF</a> /
        <a href="/${path}/?format=tape">*Tape</a>
    </p>
    <%include file="footer.mako"/>
    <hr/>
    <p>
      <span class="debug"><a href="${s3response.url}">Proxied</a></span><br/>
      <span class="debug">Took: ${s3response.total_time}</span><br/>
      <span class="debug">Attempts: ${s3response.try_count}</span>
    </p>
  </div>
        
</div>
