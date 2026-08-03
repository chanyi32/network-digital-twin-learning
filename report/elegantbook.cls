%%%%%%%%%%%%%%%%%%%%%%
%% start of file `elegantbook.cls'.
%% Copyright 2013-2022 ElegantLaTeX (elegantlatex2e@gmail.com)
%%
%% This work may be distributed and/or modified freely
%% available at https://github.com/ElegantLaTeX/ElegantBook
% 
%%%%%%%%%%%%%%%%%%%%%
% % !Mode:: "TeX:UTF-8"
\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{elegantbook}[2022/04/09 v4.3 ElegantBook document class]


%%%
\RequirePackage{kvoptions}
\RequirePackage{etoolbox}
\SetupKeyvalOptions{family=ELEGANT, prefix=ELEGANT@, setkeys=\kvsetkeys}
\newcommand{\ekv}[1]{\kvsetkeys{ELEGANT}{#1}}

% ----- Colors -----
\DeclareStringOption[blue]{color}
\DeclareStringOption[en]{lang}
\DeclareStringOption[answer]{result}
\DeclareStringOption[fancy]{mode}
\DeclareStringOption[normal]{device}
\DeclareStringOption[cm]{math}
\DeclareStringOption[marginfalse]{marginpar}
\DeclareStringOption[onecol]{toc}
\DeclareStringOption{scheme}

% ----- backward compatibility
\DeclareVoidOption{green}{\ekv{color=green}}
\DeclareVoidOption{cyan}{\ekv{color=cyan}}
\DeclareVoidOption{blue}{\ekv{color=blue}}
\DeclareVoidOption{gray}{\ekv{color=gray}}
\DeclareVoidOption{black}{\ekv{color=black}}
\DeclareVoidOption{nocolor}{\ekv{color=none}}

\DeclareVoidOption{chinese}{\ekv{scheme=chinese}}

\DeclareStringOption[ctexfont]{chinesefont}
\DeclareVoidOption{ctexfont}{\ekv{chinesefont=ctexfont}}
\DeclareVoidOption{founder}{\ekv{chinesefont=founder}}
\DeclareVoidOption{nofont}{\ekv{chinesefont=nofont}}

\DeclareVoidOption{en}{\ekv{lang=en}}
\DeclareVoidOption{cn}{\ekv{lang=cn}}
\DeclareVoidOption{it}{\ekv{lang=it}}
\DeclareVoidOption{fr}{\ekv{lang=fr}}
\DeclareVoidOption{nl}{\ekv{lang=nl}}
\DeclareVoidOption{hu}{\ekv{lang=hu}}
\DeclareVoidOption{de}{\ekv{lang=de}}
\DeclareVoidOption{mn}{\ekv{lang=mn}}
\DeclareVoidOption{pt}{\ekv{lang=pt}}
\DeclareVoidOption{jp}{\ekv{lang=jp}}

\DeclareVoidOption{fancy}{\ekv{mode=fancy}}
\DeclareVoidOption{simple}{\ekv{mode=simple}}

\DeclareVoidOption{answer}{\ekv{result=answer}}
\DeclareVoidOption{noanswer}{\ekv{result=noanswer}}

\DeclareVoidOption{normal}{\ekv{device=normal}}
\DeclareVoidOption{pad}{\ekv{device=pad}}

\DeclareStringOption[numeric-comp]{citestyle}
\DeclareStringOption[numeric]{bibstyle}

\DeclareVoidOption{newtx}{\ekv{math=newtx}}
\DeclareVoidOption{mtpro2}{\ekv{math=mtpro2}}
\DeclareVoidOption{cm}{\ekv{math=cm}}

\DeclareVoidOption{margintrue}{\ekv{marginpar=margintrue}}
\DeclareVoidOption{marginfalse}{\ekv{marginpar=marginfalse}}


\DeclareVoidOption{onecol}{\ekv{toc=onecol}}
\DeclareVoidOption{twocol}{\ekv{toc=twocol}}

\DeclareStringOption[chapter]{thmcnt}
\DeclareVoidOption{chapter}{\ekv{thmcnt=chapter}}
\DeclareVoidOption{section}{\ekv{thmcnt=section}}

\DeclareStringOption[biber]{bibend}
\DeclareVoidOption{biber}{\ekv{bibend=biber}}
\DeclareVoidOption{bibtex}{\ekv{bibend=bibtex}}


% ----- Math option -----
\newcommand\mailto[1]{\href{mailto:#1}{\nolinkurl{#1}}}

% ----- Title Style -----
\DeclareStringOption[hang]{titlestyle}[hang]
% ----- backward compatibility
\DeclareVoidOption{hang}{\ekv{titlestyle=hang}}
\DeclareVoidOption{display}{\ekv{titlestyle=display}}
% ----- Default Options -----
\DeclareDefaultOption{\PassOptionsToClass{\CurrentOption}{book}}

\ProcessKeyvalOptions*\relax
% \ProcessOptions*\relax
\LoadClass[a4paper,oneside]{book}

\RequirePackage{setspace}

\RequirePackage{csquotes}


\RequirePackage{hyperref}
\hypersetup{
  breaklinks,
  unicode,
  linktoc=all,
  bookmarksnumbered=true,
  bookmarksopen=true,
  pdfkeywords={ElegantBook},
  colorlinks,
  linkcolor=winered,
  citecolor=winered,
  urlcolor=winered,
  plainpages=false,
  pdfstartview=FitH,
  pdfborder={0 0 0},
  linktocpage
}

%% device settings
\RequirePackage{geometry}
\ifdefstring{\ELEGANT@device}{normal}{
  \geometry{
    a4paper,
    top=25.4mm, bottom=25.4mm,
    left=20mm, right=20mm,
    headheight=2.17cm,
    headsep=4mm,
    footskip=12mm
  }
  \ifdefstring{\ELEGANT@marginpar}{margintrue}{
    \geometry{
      marginparwidth=5cm, marginparsep=5mm,
      left=2cm,right=7cm}}{\relax}}{
    \relax}

\ifdefstring{\ELEGANT@device}{pad}{
\geometry{
  paperwidth=7.5in, 
  paperheight=10in,
  margin=16mm,
  headheight=2.17cm,
  footskip=4mm
}}{\relax}


\RequirePackage{indentfirst,comment}
% fontsetting
\ifdefstring{\ELEGANT@math}{mtpro2}{
  \let\Bbbk\relax
  \RequirePackage[lite]{mtpro2}
}{\relax}

\setcounter{tocdepth}{1}
\renewcommand{\baselinestretch}{1.2}

\PassOptionsToPackage{no-math}{fontspec}
\PassOptionsToPackage{quiet}{fontspec}
\RequirePackage{iftex}

\ifXeTeX
  \RequirePackage[no-math]{fontspec}
  \setmainfont{texgyretermes}[
    UprightFont = *-regular ,
    BoldFont = *-bold ,
    ItalicFont = *-italic ,
    BoldItalicFont = *-bolditalic ,
    Extension = .otf ,
    Scale = 1.0]
    
  \setsansfont{texgyreheros}[
    UprightFont = *-regular ,
    BoldFont = *-bold ,
    ItalicFont = *-italic ,
    BoldItalicFont = *-bolditalic ,
    Extension = .otf ,
    Scale = 0.9]
\else
  \RequirePackage{newtxtext}
  \RequirePackage[scaled=.90]{helvet}
\fi

\ifdefstring{\ELEGANT@lang}{cn}{
  \ifdefstring{\ELEGANT@chinesefont}{founder}{
    \RequirePackage[UTF8,scheme=plain,fontset=none]{ctex}
    \setCJKmainfont[BoldFont={FZHei-B01},ItalicFont={FZKai-Z03}]{FZShuSong-Z01}
    \setCJKsansfont[BoldFont={FZHei-B01}]{FZKai-Z03}
    \setCJKmonofont[BoldFont={FZHei-B01}]{FZFangSong-Z02}
    \setCJKfamilyfont{zhsong}{FZShuSong-Z01}
    \setCJKfamilyfont{zhhei}{FZHei-B01}
    \setCJKfamilyfont{zhkai}[BoldFont={FZHei-B01}]{FZKai-Z03}
    \setCJKfamilyfont{zhfs}[BoldFont={FZHei-B01}]{FZFangSong-Z02}
    \newcommand*{\songti}{\CJKfamily{zhsong}}
    \newcommand*{\heiti}{\CJKfamily{zhhei}}
    \newcommand*{\kaishu}{\CJKfamily{zhkai}}
    \newcommand*{\fangsong}{\CJKfamily{zhfs}}}{\relax}
  
  \ifdefstring{\ELEGANT@chinesefont}{nofont}{
    \RequirePackage[UTF8,scheme=plain,fontset=none]{ctex}}{\relax}

  \ifdefstring{\ELEGANT@chinesefont}{ctexfont}{
    \RequirePackage[UTF8,scheme=plain]{ctex}}{\relax}
  
  \AfterEndPreamble{
    \setlength\parindent{2\ccwd}}
}{\relax}

\ifcsname heiti\endcsname
  \newcommand{\cbfseries}{\heiti}
\else
  \newcommand{\cbfseries}{\bfseries}
\fi


\ifcsname kaishu\endcsname
  \newcommand{\citshape}{\kaishu}
\else
  \newcommand{\citshape}{\itshape}
\fi
\ifcsname kaishu\endcsname
  \newcommand{\cnormal}{\kaishu}
\else
  \newcommand{\cnormal}{\normalfont}
\fi

\ifcsname fangsong\endcsname
  \newcommand{\cfs}{\fangsong}
\else
  \newcommand{\cfs}{\normalfont}
\fi

\RequirePackage{anyfontsize}
\ifdefstring{\ELEGANT@math}{newtx}{
  \RequirePackage{newtxmath}
  \let\Bbbk\relax
  \RequirePackage{esint}
  %%% use yhmath pkg, uncomment following code
  % \let\oldwidering\widering
  % \let\widering\undefined
  % \RequirePackage{yhmath}
  % \let\widering\oldwidering

  %%% use esvect pkg, uncomment following code
  % \RequirePackage{esvect}

  \DeclareSymbolFont{CMlargesymbols}{OMX}{cmex}{m}{n}
  \let\sumop\relax\let\prodop\relax
  \DeclareMathSymbol{\sumop}{\mathop}{CMlargesymbols}{"50}
  \DeclareMathSymbol{\prodop}{\mathop}{CMlargesymbols}{"51}
}{\relax}


% ----- Handle Colors -----
%% ç« èŠ‚ä»¥åŠé¡µè„šå›¾å½¢

\RequirePackage[table]{xcolor}
\ifdefstring{\ELEGANT@color}{green}{
  \definecolor{structurecolor}{RGB}{0,120,2}%
  \definecolor{main}{RGB}{0,120,2}%
  \definecolor{second}{RGB}{230,90,7}%
  \definecolor{third}{RGB}{0,160,152}%
}{\relax}
\ifdefstring{\ELEGANT@color}{cyan}{
  \definecolor{structurecolor}{RGB}{31,186,190}%
  \definecolor{main}{RGB}{59,180,5}%
  \definecolor{second}{RGB}{175,153,8}%
  \definecolor{third}{RGB}{244,105,102}%
}{\relax}
\ifdefstring{\ELEGANT@color}{blue}{
  \definecolor{structurecolor}{RGB}{60,113,183}
  \definecolor{main}{RGB}{0,166,82}%
  \definecolor{second}{RGB}{255,134,24}%
  \definecolor{third}{RGB}{0,174,247}%
}{\relax}
\ifdefstring{\ELEGANT@color}{gray}{
  \definecolor{structurecolor}{RGB}{150,150,150}
  \definecolor{main}{RGB}{150,150,150}%
  \definecolor{second}{RGB}{150,150,150}%
  \definecolor{third}{RGB}{150,150,150}%
}{\relax}
\ifdefstring{\ELEGANT@color}{black}{
  \definecolor{structurecolor}{RGB}{0,0,0}
  \definecolor{main}{RGB}{0,0,0}%
  \definecolor{second}{RGB}{0,0,0}%
  \definecolor{third}{RGB}{0,0,0}%
}{\relax}

%green color
\definecolor{structure1}{RGB}{0,120,2}%
\definecolor{main1}{RGB}{0,120,2}%
\definecolor{second1}{RGB}{230,90,7}%
\definecolor{third1}{RGB}{0,160,152}%
%cyan color
\definecolor{structure2}{RGB}{31,186,190}%
\definecolor{main2}{RGB}{59,180,5}%
\definecolor{second2}{RGB}{175,153,8}%
\definecolor{third2}{RGB}{244,105,102}%
%blue color
\definecolor{structure3}{RGB}{60,113,183}
\definecolor{main3}{RGB}{0,166,82}%
\definecolor{second3}{RGB}{255,134,24}%
\definecolor{third3}{RGB}{0,174,247}%
% gray color
\definecolor{structure4}{RGB}{150,150,150}
\definecolor{main4}{RGB}{150,150,150}%
\definecolor{second4}{RGB}{150,150,150}%
\definecolor{third4}{RGB}{150,150,150}%
% black color
\definecolor{structure5}{RGB}{0,0,0}
\definecolor{main5}{RGB}{0,0,0}%
\definecolor{second5}{RGB}{0,0,0}%
\definecolor{third5}{RGB}{0,0,0}%

% corlor definition
\definecolor{winered}{rgb}{0.5,0,0}
\definecolor{bule}{RGB}{18,29,57}
\definecolor{coverlinecolor}{RGB}{10,105,190}


% ----- Title Style -----
\ifdefstring{\ELEGANT@titlestyle}{hang}{\def\style{hang}}{\relax}
\ifdefstring{\ELEGANT@titlestyle}{display}{\def\style{display}}{\relax}

% reference: 
% https://tex.stackexchange.com/questions/58506/how-to-make-a-new-command-similar-to-author
% https://pastebin.com/C8W4axzV
\newcommand\email[1]{\href{mailto:#1}{\nolinkurl{#1}}}

\global\let\@title\@empty
\global\let\@author\@empty
\global\let\@date\@empty
\newcommand{\subtitle}[1]{\gdef\@subtitle{#1}}
\newcommand{\institute}[1]{\gdef\@institute{#1}}
\newcommand{\version}[1]{\gdef\@version{#1}}
\newcommand{\extrainfo}[1]{\gdef\@extrainfo{#1}}

\RequirePackage{mwe}
\newcommand{\logo}[1]{\gdef\@logo{#1}}
\newcommand{\cover}[1]{\gdef\@cover{#1}}

\newcommand{\question}[1]{{\par\citshape #1}\\[0.2ex]}

\RequirePackage{enumerate}
% list/itemize/enumerate setting
\RequirePackage[shortlabels,inline]{enumitem}
\setlist{nolistsep}

\RequirePackage[labelfont={bf,color=structurecolor}]{caption} 
\captionsetup[table]{skip=3pt}
\captionsetup[figure]{skip=3pt}

\AtBeginDocument{
  \setlength{\abovedisplayskip}{3pt}
  \setlength{\belowdisplayskip}{3pt}
  \RequirePackage[flushmargin,stable]{footmisc}
  \setlength{\footnotesep}{12pt}
}



\RequirePackage{graphicx}
%\RequirePackage{enumerate}
\RequirePackage{amsmath,mathrsfs,amsfonts,amssymb}
% \providecommand\qed{}
% \renewcommand{\qed}{\hfill\ensuremath{\square}}
\RequirePackage{booktabs}
\RequirePackage{multicol,multirow}

\RequirePackage{fancyvrb}
\RequirePackage{makecell,lipsum,hologo}
%%ä¸­æ–‡ç»“æ„åå­—


%%   ç« èŠ‚è®¾ç½®
\RequirePackage[center,pagestyles]{titlesec}
\RequirePackage[title,titletoc,header]{appendix}


\RequirePackage[
  backend=\ELEGANT@bibend,
  citestyle=\ELEGANT@citestyle,
  bibstyle=\ELEGANT@bibstyle]{biblatex}

\ifdefstring{\ELEGANT@lang}{cn}{
  \renewcommand{\baselinestretch}{1.3}
  \renewcommand{\contentsname}{ç›®å½•}
  \renewcommand{\figurename}{å›¾}
  \renewcommand{\tablename}{è¡¨}
  \renewcommand{\partname}{\color{structurecolor}}
  \renewcommand{\thepart}{ç¬¬\zhnumber{\arabic{part}}éƒ¨åˆ†}
  \renewcommand{\listfigurename}{æ’å›¾ç›®å½•}
  \renewcommand{\listtablename}{è¡¨æ ¼ç›®å½•}
  \renewcommand{\bibname}{å‚è€ƒæ–‡çŒ®}
  \newcommand{\ebibname}{å‚è€ƒæ–‡çŒ®}
  \renewcommand{\appendixname}{é™„å½•}
  \renewcommand{\appendixtocname}{é™„å½•}
  \renewcommand{\indexname}{ç´¢\hspace{2em}å¼•}
  \newcommand\figref[1]{\textbf{å›¾}~\ref{#1}}
  \newcommand\tabref[1]{\textbf{è¡¨}~\ref{#1}}
  \newcommand{\authorname}{\citshape ä½œè€…ï¼š}
  \newcommand{\institutename}{\citshape ç»„ç»‡ï¼š}
  \newcommand{\datename}{\citshape æ—¶é—´ï¼š}
  \newcommand{\versionname}{\citshape ç‰ˆæœ¬ï¼š}
  \newcommand{\notename}{ç¬”è®°}
  \renewcommand*{\proofname}{è¯æ˜}
  \newcommand{\definitionname}{å®šä¹‰}
  \newcommand{\theoremname}{å®šç†}
  \newcommand{\axiomname}{å…¬ç†}
  \newcommand{\postulatename}{å…¬è®¾}
  \newcommand{\lemmaname}{å¼•ç†}
  \newcommand{\propositionname}{å‘½é¢˜}
  \newcommand{\corollaryname}{æ¨è®º}
  \newcommand{\examplename}{ä¾‹é¢˜} %
  \newcommand{\instancename}{ç¤ºä¾‹} %
  \newcommand{\problemname}{é—®é¢˜} % é—®é¢˜
  \newcommand{\exercisename}{ç»ƒä¹ } % ç»ƒä¹ =ä¹ é¢˜
  \newcommand{\remarkname}{æ³¨}
  \newcommand{\assumptionname}{å‡è®¾}
  \newcommand{\conclusionname}{ç»“è®º}
  \newcommand{\solutionname}{è§£}
  \newcommand{\propertyname}{æ€§è´¨}
  \newcommand{\introductionname}{å†…å®¹æè¦}
  \newcommand\bioinfo[2]{\gdef\@bioinfo{{\citshape #1}ï¼š#2}}
  \newcommand{\updatename}{æ›´æ–°ï¼š}
  \newcommand{\historyname}{ç‰ˆæœ¬æ›´æ–°å†å²}
  \newcommand{\beforechap}{ç¬¬}
  \newcommand{\afterchap}{ç« }
}{\relax}


\ifdefstring{\ELEGANT@lang}{en}{
  \setlength\parindent{2em}
  \newcommand\figref[1]{\textbf{Figure}~\ref{#1}}
  \newcommand\tabref[1]{\textbf{Table}~\ref{#1}}
  \renewcommand{\chaptername}{Chapter}
  \renewcommand{\partname}{\color{structurecolor} Part}
  \newcommand{\authorname}{\textbf{Author: }}
  \newcommand{\institutename}{\textbf{Institute: }}
  \newcommand{\datename}{\textbf{Date: }}
  \newcommand{\versionname}{\textbf{Version: }}
  \newcommand{\notename}{Note}
  \newcommand{\proofname}{Proof}
  \newcommand{\problemname}{Problem}
  \newcommand{\definitionname}{Definition}
  \newcommand{\theoremname}{Theorem}
  \newcommand{\axiomname}{Axiom}
  \newcommand{\postulatename}{Postulate}
  \newcommand{\lemmaname}{Lemma}
  \newcommand{\propositionname}{Proposition}
  \newcommand{\corollaryname}{Corollary}
  \newcommand{\examplename}{Example}
  \newcommand{\exercisename}{Exercise}
  \newcommand{\remarkname}{Remark}
  \newcommand{\assumptionname}{Assumption}
  \newcommand{\conclusionname}{Conclusion}
  \newcommand{\solutionname}{Solution}
  \newcommand{\propertyname}{Property}
  \newcommand{\introductionname}{Introduction}
  \renewcommand{\appendixname}{Appendix}
  \newcommand{\ebibname}{Bibliography}
  % \newcommand{\problemsetname}{Exercise}
  \newcommand\bioinfo[2]{\gdef\@bioinfo{\textbf{#1}: #2}}
  \newcommand{\updatename}{Updates:}
  \newcommand{\historyname}{Version History}
}{\relax}

\ifdefstring{\ELEGANT@lang}{it}{
  % \RequirePackage[utf8]{inputenc}
  \RequirePackage[italian]{babel}
  % \RequirePackage[T1]{fontenc}
  \setlength\parindent{2em}
  \newcommand\figref[1]{\textbf{Figura}~\ref{#1}}
  \newcommand\tabref[1]{\textbf{Tabella}~\ref{#1}}
  \renewcommand{\chaptername}{Chapter}
  \newcommand{\authorname}{\textbf{Autore: }}
  \newcommand{\institutename}{\textbf{Istituto: }}
  \newcommand{\datename}{\textbf{Data: }}
  \newcommand{\versionname}{\textbf{Versione: }}
  \newcommand{\notename}{Nota}
  \newcommand{\proofname}{Dimostrazione}
  \newcommand{\problemname}{Problema}
  \newcommand{\definitionname}{Definizione}
  \newcommand{\theoremname}{Teorema}
  \newcommand{\axiomname}{Assioma}
  \newcommand{\postulatename}{Postulato}
  \newcommand{\lemmaname}{Lemma}
  \newcommand{ç´¶‰ËkºwµçUÑ•ÈÍ•ÀôÁÁÑt…Ğ€¡q±¥¹•İ¥‘Ñ µİ¥‘Ñ °À¤ì(€€€€€€€€€qÑ•áÑ½±½ÉíÑ¡¥É‘õì‘qÍÁ…‘•ÍÕ¥Ğ‘õôíõô±ô(€€”q¹•İÑ‰Ñ¡•½É•µm…ÕÑ¼½Õ¹Ñ•È±¹Õµ‰•Èİ¥Ñ¡¥¸õ¡…ÁÑ•Éuí‘•™¥¹¥Ñ¥½¹õíq‘•™¥¹¥Ñ¥½¹¹…µ•õí‘•™ÍÑå±•õí‘•™ô(€q•±…É•Q½±½É	½ám…ÕÑ¼½Õ¹Ñ•È±¹Õµ‰•Èİ¥Ñ¡¥¸õq19QÑ¡µ¹Ñuí‘•™¥¹¥Ñ¥½¹õìœ¼Ñq±…‰•°œõì(€€€½µµ½¸±‘•™ÍÑå±”°(€€€%™Y…±Õ•QõìŒÅô(€€€€€íÑ¥Ñ±”õíq‘•™¥¹¥Ñ¥½¹¹…µ•ùqÑ¡•Ñ‰½Õ¹Ñ•Ép€ ŒÄ¥õô(€€€€€ì(€€€€€€€%™Y…±Õ•QõìŒÉô€(€€€€€€€€€íÑ¥Ñ±”õíq‘•™¥¹¥Ñ¥½¹¹…µ•ùqÑ¡•Ñ‰½Õ¹Ñ•Ép€ ŒÈ¥õô(€€€€€€€€€íÑ¥Ñ±”õq‘•™¥¹¥Ñ¥½¹¹…µ•ùqÑ¡•Ñ‰½Õ¹Ñ•Éô(€€€€€ô°(€€€%™	½½±•…¹QõìŒÍõí±…‰•°ôŒÑõí±…‰•°õí‘•˜èŒÑõõô(€€”q¹•İÑ‰Ñ¡•½É•µm…ÕÑ¼½Õ¹Ñ•È±¹Õµ‰•Èİ¥Ñ¡¥¸õ¡…ÁÑ•ÉuíÑ¡•½É•µõíqÑ¡•½É•µ¹…µ•õíÑ¡µÍÑå±•õíÑ¡µô(€q•±…É•Q½±½É	½ám…ÕÑ¼½Õ¹Ñ•È±¹Õµ‰•Èİ¥Ñ¡¥¸õq19QÑ¡µ¹ÑuíÑ¡•½É•µõìœ¼Ñq±…‰•°œõì(€€€½µµ½¸±Ñ¡µÍÑå±”°(€€€%™Y…±Õ•QõìŒÅô(€€€€€íÑ¥Ñ±”õíqÑ¡•½É•µ¹…µ•ùqÑ¡•Ñ‰½Õ¹Ñ•Ép€ ŒÄ¥õô(€€€€€ì(€€€€€€€%™Y…±Õ•QõìŒÉô€(€€€€€€€€€íÑ¥Ñ±”õíqÑ¡•½É•µ¹…µ•ùqÑ¡•Ñ‰½Õ¹Ñ•Ép€ ŒÈ¥õô(€€€€€€€€€íÑ¥Ñ±”õqÑ¡•½É•µ¹…µ•ùqÑ¡•Ñ‰½Õ¹Ñ•Éô(€€€€€ô°(€€€%™	½½±•…¹QõìŒÍõí±…‰•°ôŒÑõí±…‰•°õíÑ¡´èŒÑõõô(€€”q¹•İÑ‰Ñ¡•½É•µm…ÕÑ¼½Õ¹Ñ•È±¹Õµ‰•Èİ¥Ñ¡¥¸õ¡…ÁÑ•ÉuíÁ½ÍÑÕ±…Ñ•õíqÁ½ÍÑÕ±…Ñ•¹…µ•õíÑ¡µÍÑå±•õíÁ½Íô(€q•±…É•Q½±½É	½ám…ÕÑ¼½Õ¹Ñ•È±¹Õµ‰•Èİ¥Ñ¡¥¸õq19QÑ¡µ¹ÑuíÁ½ÍÑÕ±…Ñ•õìœ¼Ñq±…‰•°œõì(€€€½µµ½¸±Ñ¡µÍÑå±”°(€€€%™Y…±Õ•QõìŒÅô(€€€€€íÑ¥Ñ±”õíqÁ½ÍÑÕ±…Ñ•¹…µ•ùqÑ¡•Ñ‰½Õ¹Ñ•Ép€ ŒÄ¥õô(€€€€€ì(€€€€€€€%™Y…±Õ•QõìŒÉô€(€€€€€€€€€íÑ¥Ñ±”õíqÁ½ÍÑÕ±…Ñ•¹…µ•ùqÑ¡•Ñ‰½Õ¹Ñ•Ép€ ŒÈ¥õô(€€€€€€€€€íÑ¥Ñ±”õqÁ½ÍÑÕ±…Ñ•¹…µ•ùqÑ¡•Ñ‰½Õ¹Ñ•Éô(€€€€€ô°(€€€%™	½½±•…¹QõìŒÍõí±…‰•°ôŒÑõí±…‰•°õíÁ½ÌèŒÑõõô(€€”q¹•İÑ‰Ñ¡•½É•µm…ÕÑ¼½Õ¹Ñ•È±¹Õµ‰•Èİ¥Ñ¡¥¸õ¡…ÁÑ•Éuí…á¥½µõíq…á¥½µ¹…µ•õíÑ¡µÍÑå±•õí…á¥ô(€q•±…É•Q½±½É	½ám…ÕÑ¼½Õ¹Ñ•È±¹Õµ‰•Èİ¥Ñ¡¥¸õq19QÑ¡µ¹Ñuí…á¥½µõìœ¼Ñq±…‰•°œõì(€€€½µµ½¸±Ñ¡µÍÑå±”°(€€€%™Y…±Õ•QõìŒÅô(€€€€€íÑ¥Ñ±”õíq…á¥½µ¹…µ•ùqÑ¡•Ñ‰½Õ¹Ñ•Ép€ ŒÄ¥õô(€€€€€ì(€€€€€€€%™Y…±Õ•QõìŒÉô€(€€€€€€€€€íÑ¥Ñ±”õíq…á¥½µ¹…µ•ùqÑ¡•Ñ‰½Õ¹Ñ•Ép€ ŒÈ¥õô(€€€€€€€€€íÑ¥Ñ±”õq…á¥½µ¹…µ•ùqÑ¡•Ñ‰½Õ¹Ñ•Éô(€€€€€ô°(€€€%™	½½±•…¹QõìŒÍõí±…‰•°ôŒÑõí±…‰•°õí…á¤èŒÑõõô(€€”q¹•İÑ‰Ñ¡•½É•µm…ÕÑ¼½Õ¹Ñ•È±¹Õµ‰•Èİ¥Ñ¡¥¸õ¡…ÁÑ•Éuí½É½±±…Éåõíq½É½±±…Éå¹…µ•õíÑ¡µÍÑå±•õí½Éô(€q•±…É•Q½±½É	½ám…ÕÑ¼½Õ¹Ñ•È±¹Õµ‰•Èİ¥Ñ¡¥¸õq19QÑ¡µ¹Ñuí½É½±±…Éåõìœ¼Ñq±…‰•°œõì(€€€½µµ½¸±Ñ¡µÍÑå±”°(€€€%™Y…±Õ•QõìŒÅô(€€€€€íÑ¥Ñ±”õíq½É½±±…Éå¹…µ•ùqÑ¡•Ñ‰½Õ¹Ñ•Ép€ ŒÄ¥õô(€€€€€ì(€€€€€€€%™Y…±Õ•QõìŒÉô€(€€€€€€€€€íÑ¥Ñ±”õíq½É½±±…Éå¹…µ•ùqÑ¡•Ñ‰½Õ¹Ñ•Ép€ ŒÈ¥õô(€€€€€€€€€íÑ¥Ñ±”õq½É½±±…Éå¹…µ•ùqÑ¡•Ñ‰½Õ¹Ñ•Éô(€€€€€ô°(€€€%™	½½±•…¹QõìŒÍõí±…‰•°ôŒÑõí±…‰•°õí½ÈèŒÑõõô(€€”q¹•İÑ‰Ñ¡•½É•µm…ÕÑ¼½Õ¹Ñ•È±¹Õµ‰•Èİ¥Ñ¡¥¸õ¡…ÁÑ•Éuí±•µµ…õíq±•µµ…¹…µ•õíÑ¡µÍÑå±•õí±•µô(€q•±…É•Q½±½É	½ám…ÕÑ¼½Õ¹Ñ•È±¹Õµ‰•Èİ¥Ñ¡¥¸õq19QÑ¡µ¹Ñuí±•µµ…õìœ¼Ñq±…‰•°œõì(€€€½µµ½¸±Ñ¡µÍÑå±”°(€€€%™Y…±Õ•QõìŒÅô(€€€€€íÑ¥Ñ±”õíq±•µµ…¹…µ•ùqÑ¡•Ñ‰½Õ¹Ñ•Ép€ ŒÄ¥õô(€€€€€ì(€€€€€€€%™Y…±Õ•QõìŒÉô€(€€€€€€€€€íÑ¥Ñ±”õíq±•µµ…¹…µ•ùqÑ¡•Ñ‰½Õ¹Ñ•Ép€ ŒÈ¥õô(€€€€€€€€€íÑ¥Ñ±”õq±•µµ…¹…µ•ùqÑ¡•Ñ‰½Õ¹Ñ•Éô(€€€€€ô°(€€€%™	½½±•…¹QõìŒÍõí±…‰•°ôŒÑõí±…‰•°õí±•´èŒÑõõô(€€”q¹•İÑ‰Ñ¡•½É•µm…ÕÑ¼½Õ¹Ñ•È±¹Õµ‰•Èİ¥Ñ¡¥¸õ¡…ÁÑ•ÉuíÁÉ½Á½Í¥Ñ¥½¹õíqÁÉ½Á½Í¥Ñ¥½¹¹…µ•õíÁÉ½ÁÍÑå±•õíÁÉ½ô(€q•±…É•Q½±½É	½ám…ÕÑ¼½Õ¹Ñ•È±¹Õµ‰•Èİ¥Ñ¡¥¸õq19QÑ¡µ¹ÑuíÁÉ½Á½Í¥Ñ¥½¹õìœ¼Ñq±…‰•°œõì(€€€½µµ½¸±ÁÉ½ÁÍÑå±”°(€€€%™Y…±Õ•QõìŒÅô(€€€€€íÑ¥Ñ±”õíqÁÉ½Á½Í¥Ñ¥½¹¹…µ•ùqÑ¡•Ñ‰½Õ¹Ñ•Ép€ ŒÄ¥õô(€€€€€ì(€€€€€€€%™Y…±Õ•QõìŒÉô€(€€€€€€€€€íÑ¥Ñ±”õíqÁÉ½Á½Í¥Ñ¥½¹¹…µ•ùqÑ¡•Ñ‰½Õ¹Ñ•Ép€ ŒÈ¥õô(€€€€€€€€€íÑ¥Ñ±”õqÁÉ½Á½Í¥Ñ¥½¹¹…µ•ùqÑ¡•Ñ‰½Õ¹Ñ•Éô(€€€€€ô°(€€€%™	½½±•…¹QõìŒÍõí±…‰•°ôŒÑõí±…‰•°õíÁÉ¼èŒÑõõô)õíqÉ•±…áô(()q¥™‘•™ÍÑÉ¥¹íq19Qµ½‘•õíÍ¥µÁ±•õì(€q±•Ñq½Á•¹‰½áqÉ•±…à(€qI•ÅÕ¥É•A…­…•í…µÍÑ¡µô(€q±•ÑqÁÉ½½™qÉ•±…à(€€”q±•ÑqÁÉ½½™¹…µ•qÉ•±…à(€q±•Ñq•¹‘ÁÉ½½™qÉ•±…à((€€”‘•±…É”„¹•ÜÑ¡•½É•´ÍÑå±”(€q¹•İÑ¡•½É•µÍÑå±•í‘•™ÍÑå±•õìÍÁÑõìÍÁÑõíq¥ÑÍ¡…Á•õì´ÍÁÑõì(€€€q‰™Í•É¥•Íq½±½Éíµ…¥¹õõíõìÀ¸Õ•µõíqÑ¡µ¹…µ•ìŒÅôqÑ¡µ¹Õµ‰•ÉìŒÉôqÑ¡µ¹½Ñ•ì ŒÌ¥õô(€q¹•İÑ¡•½É•µÍÑå±•íÑ¡µÍÑå±•õìÍÁÑõìÍÁÑõíq¥ÑÍ¡…Á•õì´ÍÁÑõì(€€€q‰™Í•É¥•Íq½±½ÉíÍ•½¹‘õõíõìÀ¸Õ•µõíqÑ¡µ¹…µ•ìŒÅôqÑ¡µ¹Õµ‰•ÉìŒÉôqÑ¡µ¹½Ñ•ì ŒÌ¥õô(€q¹•İÑ¡•½É•µÍÑå±•íÁÉ½ÍÑå±•õìÍÁÑõìÍÁÑõíq¥ÑÍ¡…Á•õì´ÍÁÑõì(€€€q‰™Í•É¥•Íq½±½ÉíÑ¡¥É‘õõíõìÀ¸Õ•µõíqÑ¡µ¹…µ•ìŒÅôqÑ¡µ¹Õµ‰•ÉìŒÉôqÑ¡µ¹½Ñ•ì ŒÌ¥õô(((€qÑ¡•½É•µÍÑå±•í‘•™ÍÑå±•ô€”‘•™¥¹¥Ñ¥½¸ÍÑå±”(€q¹•İÑ¡•½É•µí‘•™¥¹¥Ñ¥½¹õíq‘•™¥¹¥Ñ¥½¹¹…µ•õmq19QÑ¡µ¹Ñt((€qÑ¡•½É•µÍÑå±•íÑ¡µÍÑå±•ô€•Ñ¡•½É•´ÍÑå±”(€q¹•İÑ¡•½É•µíÑ¡•½É•µõíqÑ¡•½É•µ¹…µ•õmq19QÑ¡µ¹Ñt(€q¹•İÑ¡•½É•µí±•µµ…õíq±•µµ…¹…µ•õmq19QÑ¡µ¹Ñt(€q¹•İÑ¡•½É•µí½É½±±…Éåõíq½É½±±…Éå¹…µ•õmq19QÑ¡µ¹Ñt(€q¹•İÑ¡•½É•µíÁ½ÍÑÕ±…Ñ•õíqÁ½ÍÑÕ±…Ñ•¹…µ•õmq19QÑ¡µ¹Ñt(€q¹•İÑ¡•½É•µí…á¥½µõíq…á¥½µ¹…µ•õmq19QÑ¡µ¹Ñt((€qÑ¡•½É•µÍÑå±•íÁÉ½ÍÑå±•ô€”ÁÉ½Á½Í¥Ñ¥½¸ÍÑå±”(€q¹•İÑ¡•½É•µíÁÉ½Á½Í¥Ñ¥½¹õíqÁÉ½Á½Í¥Ñ¥½¹¹…µ•õmq19QÑ¡µ¹Ñt)õíqÉ•±…áô((”µ…¥»¾ò!É••¸µ‘•˜¤è•á…µÁ±”•á•É¥Í”ÁÉ½‰±•´Í½±ÕÑ¥½¸(”Í•½¹“¾ò!½É…¹”µÑ¡·¾ò$èÁÉ½½˜¹½Ñ”É•µ…É¬€€(”Ñ¡¥É“¾ò!‰±Õ”µÁÉ½À¤è€…ÍÍÕµÁÑ¥½¹ÌÁÉ½Á•ÉÑä½¹±ÕÍ¥½¸ÕÍÑ½´((””á…µÁ±”İ¥Ñ ½Õ¹Ñ•È)q¹•İ½Õ¹Ñ•Éí•á…µõm¡…ÁÑ•Ét)qÍ•Ñ½Õ¹Ñ•Éí•á…µõìÁô)qÉ•¹•İ½µµ…¹‘íqÑ¡••á…µõíqÑ¡•¡…ÁÑ•È¹q…É…‰¥í•á…µõô)q¹•İ•¹Ù¥É½¹µ•¹Ñí•á…µÁ±•õlÅumuì(€qÉ•™ÍÑ•Á½Õ¹Ñ•Éí•á…µô(€qÁ…Éq¹½¥¹‘•¹ÑqÑ•áÑ‰™íq½±½Éíµ…¥¹õíq•á…µÁ±•¹…µ•ôqÑ¡••á…´€ŒÄõqÉµ™…µ¥±åõì(€qÁ…Éq¥¹½É•ÍÁ…•Í…™Ñ•É•¹‘ô((””á•É¥Í”İ¥Ñ ½Õ¹Ñ•È)q¹•İ½Õ¹Ñ•Éí•á•Éõm¡…ÁÑ•Ét)qÍ•Ñ½Õ¹Ñ•Éí•á•ÉõìÁô)qÉ•¹•İ½µµ…¹‘íqÑ¡••á•ÉõíqÑ¡•¡…ÁÑ•È¹q…É…‰¥í•á•Éõô)q¹•İ•¹Ù¥É½¹µ•¹Ñí•á•É¥Í•õlÅumuì(€qÉ•™ÍÑ•Á½Õ¹Ñ•Éí•á•Éô(€qÁ…Éq¹½¥¹‘•¹Ñqµ…­•‰½ál´ÍÁÑumÉuì(€€€qÍÉ¥ÁÑÍ¥é•q½±½ÉíÉ•„äÁõq!…¹‘A•¹¥±1•™ÑqÅÕ…‘ô(€€€qÑ•áÑ‰™íq½±½Éíµ…¥¹õíq•á•É¥Í•¹…µ•ôqÑ¡••á•È€ŒÄõqÉµ™…µ¥±åõì(€€€qÁ…Éq¥¹½É•ÍÁ…•Í…™Ñ•É•¹‘ô((””AÉ½‰±•´İ¥Ñ ½Õ¹Ñ•È)q¹•İ½Õ¹Ñ•ÉíÁÉ½‰õm¡…ÁÑ•Ét)qÍ•Ñ½Õ¹Ñ•ÉíÁÉ½‰õìÁô)qÉ•¹•İ½µµ…¹‘íqÑ¡•ÁÉ½‰õíqÑ¡•¡…ÁÑ•È¹q…É…‰¥íÁÉ½‰õô)q¹•İ•¹Ù¥É½¹µ•¹ÑíÁÉ½‰±•µõlÅumuì(€qÉ•™ÍÑ•Á½Õ¹Ñ•ÉíÁÉ½‰ô(€qÁ…Éq¹½¥¹‘•¹ÑqÑ•áÑ‰™íq½±½Éíµ…¥¹õíqÁÉ½‰±•µ¹…µ•ôqÑ¡•ÁÉ½ˆ€ŒÄõqÉµ™…µ¥±åõì(€qÁ…Éq¥¹½É•ÍÁ…•Í…™Ñ•É•¹‘ô()q¹•İ•¹Ù¥É½¹µ•¹Ñí¹½Ñ•õì(€qÁ…Éq¹½¥¹‘•¹Ñqµ…­•‰½ál´ÍÁÑumÉuì(€€€qÍÉ¥ÁÑÍ¥é•q½±½ÉíÉ•„äÁõqÑ•áÑ‘‰•¹‘qÅÕ…‘ô(€€€qÑ•áÑ‰™íq½±½ÉíÍ•½¹‘õq¹½Ñ•¹…µ•ôq¥ÑÍ¡…Á•õíqÁ…Éô()q¹•İ•¹Ù¥É½¹µ•¹ÑíÁÉ½½™õì(€qÁ…Éq¹½¥¹‘•¹ÑqÑ•áÑ‰™íq½±½ÉíÍ•½¹‘õqÁÉ½½™¹…µ•píô(€q½±½Éí‰±…¬„äÁõq™Íõì(€€”q¡™¥±°‘q	½à‘qÅÕ…(€qÁ…Éô()q¹•İ•¹Ù¥É½¹µ•¹ÑíÍ½±ÕÑ¥½¹õíqÁ…Éq¹½¥¹‘•¹ÑqÑ•áÑ‰™íq½±½Éíµ…¥¹õqÍ½±ÕÑ¥½¹¹…µ•ôq¥ÑÍ¡…Á•õíqÁ…Éô)q¹•İ•¹Ù¥É½¹µ•¹ÑíÉ•µ…É­õíq¹½¥¹‘•¹ÑqÑ•áÑ‰™íq½±½ÉíÍ•½¹‘õqÉ•µ…É­¹…µ•õõíqÁ…Éô)q¹•İ•¹Ù¥É½¹µ•¹Ñí…ÍÍÕµÁÑ¥½¹õíqÁ…Éq¹½¥¹‘•¹ÑqÑ•áÑ‰™íq½±½ÉíÑ¡¥É‘õq…ÍÍÕµÁÑ¥½¹¹…µ•ôq¥ÑÍ¡…Á•õíqÁ…Éô)q¹•İ•¹Ù¥É½¹µ•¹Ñí½¹±ÕÍ¥½¹õíqÁ…Éq¹½¥¹‘•¹ÑqÑ•áÑ‰™íq½±½ÉíÑ¡¥É‘õq½¹±ÕÍ¥½¹¹…µ•ôq¥ÑÍ¡…Á•õíqÁ…Éô)q¹•İ•¹Ù¥É½¹µ•¹ÑíÁÉ½Á•ÉÑåõíqÁ…Éq¹½¥¹‘•¹ÑqÑ•áÑ‰™íq½±½ÉíÑ¡¥É‘õqÁÉ½Á•ÉÑå¹…µ•ôq¥ÑÍ¡…Á•õíqÁ…Éô)q¹•İ•¹Ù¥É½¹µ•¹ÑíÕÍÑ½µõlÅuíqÁ…Éq¹½¥¹‘•¹ÑqÑ•áÑ‰™íq½±½ÉíÑ¡¥É‘ô€ŒÅôq¥ÑÍ¡…Á•õíqÁ…Éô()qI•ÅÕ¥É•A…­…•íµÕ±Ñ¥½±ô)qÑ‰Í•Ñì(€¥¹ÑÉ½‘ÕÑ¥½¹ÍÑä¼¹ÍÑå±”õì(€€€•¹¡…¹•°(€€€‰É•…­…‰±”°(€€€½±‰…¬õÍÑÉÕÑÕÉ•½±½È„ÄÀ°(€€€½±™É…µ”õÍÑÉÕÑÕÉ•½±½È°(€€€™½¹ÑÑ¥Ñ±”õq‰™Í•É¥•Ì°(€€€½±‰…­Ñ¥Ñ±”õÍÑÉÕÑÕÉ•½±½È°(€€€™½¹ÑÕÁÁ•Èõq¥ÑÍ¡…Á”°(€€€…ÑÑ… ‰½á•Ñ¥Ñ±”Ñ¼Ñ½À•¹Ñ•ÈõíåÍ¡¥™Ğô´Íµ´±åÍ¡¥™ÑÑ•áĞô´Åµµô°(€€€‰½áÉÕ±”ôÁÁĞ°(€€€Ñ½ÁÉÕ±”ôÀ¸ÕÁĞ°(€€€‰½ÑÑ½µÉÕ±”ôÀ¸ÕÁĞ°(€€€Ñ½ÀôáÁĞ°(€€€‰•™½É”Í­¥ÀôáÁĞ°(€€€Í¡…ÉÀ½É¹•ÉÌ(€ô°)ô()q¹•İ•¹Ù¥É½¹µ•¹Ñí¥¹ÑÉ½‘ÕÑ¥½¹õlÅumq¥¹ÑÉ½‘ÕÑ¥½¹¹…µ•uì(€q‰•¥¹íÑ½±½É‰½áõm¥¹ÑÉ½‘ÕÑ¥½¹ÍÑä±Ñ¥Ñ±”õìŒÅõt(€€€q‰•¥¹íµÕ±Ñ¥½±ÍõìÉô(€€€€€q‰•¥¹í¥Ñ•µ¥é•õm±…‰•°õqÑ•áÑ½±½ÉíÍÑÉÕÑÕÉ•½±½ÉõíqÕÁÍ¡…Á•qÍÉ¥ÁÑÍ¥é•qMÅÕ…É•M¡…‘½İ	½ÑÑ½µI¥¡Ñõuõì(€€€€€q•¹‘í¥Ñ•µ¥é•ô(€€€q•¹‘íµÕ±Ñ¥½±Íô(€q•¹‘íÑ½±½É‰½áõô()qI•ÅÕ¥É•A…­…•í…‘™½É¹ô()q¹•İ•¹Ù¥É½¹µ•¹ÑíÁÉ½‰±•µÍ•ÑõlÅumqá¡…ÁÑ•ÉÑ¥Ñ±•ùq•á•É¥Í•¹…µ•uì(€qÙÍÁ…”©ìÄÁÁÑô(€q‰•¥¹í•¹Ñ•Éô(€€€qÁ¡…¹Ñ½µÍ•Ñ¥½¹q…‘‘½¹Ñ•¹ÑÍ±¥¹•íÑ½õíÍ•Ñ¥½¹õíqÑ•á½ÉÁ‘™ÍÑÉ¥¹íqá¡…ÁÑ•ÉÑ¥Ñ±•ùq•á•É¥Í•¹…µ•õíq•á•É¥Í•¹…µ•õô(€€€€”qµ…É­‰½Ñ¡ìŒÅõíqÉ¥¡Ñµ…É­ô(€€€qµ…É­É¥¡ÑìŒÅô(€€€qÑ•áÑ½±½ÉíÍÑÉÕÑÕÉ•½±½Éõíq1…É•q‰™Í•É¥•Íq…‘™ÑÉ¥Á±•™±½ÕÉ¥Í¡±•™ÑøŒÅùq…‘™ÑÉ¥Á±•™±½ÕÉ¥Í¡É¥¡Ñô(€q•¹‘í•¹Ñ•Éô(€q‰•¥¹í•¹Õµ•É…Ñ•õõì(€q•¹‘í•¹Õµ•É…Ñ•õô()q‘•™qÉ•±Í•íq•¹‘É½ÕÀÍÑ…ÉÑô)q‘•™q•¹‘É•±Í•í•¹‘q‰•¥¹É½ÕÁq‘•˜qÕÉÉ•¹Ù¥ÈíÉ•±Í•õô()q¥™‘•™ÍÑÉ¥¹íq19QÉ•ÍÕ±Ñõí¹½…¹Íİ•Éõì(€qÑ	•¥¹½Õµ•¹Ñì(€q•á±Õ‘•½µµ•¹ÑíÍ½±ÕÑ¥½¹ô(€q•á±Õ‘•½µµ•¹ÑíÁÉ½½™ô(€q•á±Õ‘•½µµ•¹Ñí¥¹±¥¹•ô(€ô)õíqÉ•±…áô(((—¦†×r'¦†×¢h)qI•ÅÕ¥É•A…­…•í™…¹å¡‘Éô)q™…¹å¡™íô(()q™…¹å™½½Ñmuíq½±½ÉíÍÑÉÕÑÕÉ•½±½ÉõqÍµ…±±qÑ¡•Á…•ô)q¥™Ñİ½Í¥‘”(€q™…¹å¡•…‘m1uíq½±½ÉíÍÑÉÕÑÕÉ•½±½Éõq¹½Éµ…±q±•™Ñµ…É­ô(€q™…¹å¡•…‘m=Iuíq½±½ÉíÍÑÉÕÑÕÉ•½±½Éõq¹½Éµ…±qÉ¥¡Ñµ…É­ô)q•±Í”(€q™…¹å¡•…‘mIuíq½±½ÉíÍÑÉÕÑÕÉ•½±½Éõq¹½Éµ…±qÉ¥¡Ñµ…É­ô)q™¤()qÉ•¹•İ½µµ…¹‘íq¡•…‘ÉÕ±•õíq½±½ÉíÍÑÉÕÑÕÉ•½±½Éõq¡ÉÕ±”İ¥‘Ñ¡qÑ•áÑİ¥‘Ñ¡ô)qÁ…•ÍÑå±•í™…¹åô)qÉ•¹•İ½µµ…¹‘íq¡•…‘ÉÕ±•İ¥‘Ñ¡õìÅÁÑô(”qÉ•¹•İ½µµ…¹‘íq¡•…‘ÉÕ±•õíô)q™…¹åÁ…•ÍÑå±•íÁ±…¥¹õíqÉ•¹•İ½µµ…¹‘íq¡•…‘ÉÕ±•İ¥‘Ñ¡õìÁÁÑõq™…¹å¡™íõqÉ•¹•İ½µµ…¹‘íq¡•…‘ÉÕ±•õíõô)qÉ•¹•İ½µµ…¹‘íqÍ•Ñ¥½¹µ…É­õlÅuíqµ…É­É¥¡ÑíqÑ¡•Í•Ñ¥½¹p°€ŒÅõíõô)qÉ•¹•İ½µµ…¹‘íq¡…ÁÑ•Éµ…É­õlÅuíqµ…É­‰½Ñ¡íqá¡…ÁÑ•ÉÑ¥Ñ±•p°€ŒÅõíõô(()qÉ•¹•İ½µµ…¹©íqµ…­•Ñ¥Ñ±•õì”)q¡åÁ•ÉÍ•ÑÕÁíÁ…•…¹¡½Èõ™…±Í•ô)qÁ…•¹Õµ‰•É¥¹í±Á¡ô)q‰•¥¹íÑ¥Ñ±•Á…•ô(€q¹•İ•½µ•ÑÉåíµ…É¥¸€ô€Á¥¹ô(€qÁ…É¥¹‘•¹ĞôÁÁĞ(€q¥™‘•™ÍÑÉ¥¹íq19Q‘•Ù¥•õí¹½Éµ…±õì(€€€q¥™Í¹…µ”½Ù•Éq•¹‘Í¹…µ”(€€€€€q¥¹±Õ‘•É…Á¡¥Ímİ¥‘Ñ õq±¥¹•İ¥‘Ñ¡uíq½Ù•Éô(€€€q•±Í”(€€€€€q¥¹±Õ‘•É…Á¡¥Ímİ¥‘Ñ õq±¥¹•İ¥‘Ñ¡uí•á…µÁ±”µ¥µ…•ô(€€€q™¤(€õíqÉ•±…áô(€q¥™‘•™ÍÑÉ¥¹íq19Q‘•Ù¥•õíÁ…‘õì(€€€q¥™Í¹…µ”½Ù•Éq•¹‘Í¹…µ”(€€€€€q¥¹±Õ‘•É…Á¡¥ÍmÑÉ¥´ôÀ€ÈÙ‰À€À€ÈÙ‰À±±¥ÀõÑÉÕ”°İ¥‘Ñ õq±¥¹•İ¥‘Ñ¡uíq½Ù•Éô(€€€q•±Í”(€€€€€q¥¹±Õ‘•É…Á¡¥ÍmÑÉ¥´ôÀ€ÈÙ‰À€À€ÈÙ‰À±±¥ÀõÑÉÕ”°İ¥‘Ñ õq±¥¹•İ¥‘Ñ¡uí•á…µÁ±”µ¥µ…•ô(€€€q™¤(€õíqÉ•±…áô(€qÍ•Ñ±•¹Ñ¡íq™‰½áÍ•ÁõìÁÁÑô(€q½±½É‰½áí½Ù•É±¥¹•½±½Éõíqµ…­•‰½ámq±¥¹•İ¥‘Ñ¡umuíqÍ¡½ÉÑÍÑ…­muíqÙÍÁ…•ìÀ¸Õ¥¹õõõô(€qÙ™¥±°(€qÙÍ­¥À´É•à(€q¡ÍÁ…•ìÉ•µô(€qÁ…É‰½áìÀ¸áqÑ•áÑİ¥‘Ñ¡õì(€€€q‰™Í•É¥•Íq!Õ”€(€€€€€q¥™Í¹…µ”Ñ¥Ñ±•q•¹‘Í¹…µ”qÑ¥Ñ±”q™¤(€€€qÁ…Éô(€qÙ™¥±°(€qÙÍÁ…•ì´Ä¸Áµô(€qÍ•ÑÍÑÉ•Ñ¡ìÈ¸Õô(€q¡ÍÁ…•ìÈ¸Õ•µô(€q‰•¥¹íµ¥¹¥Á…•õmuìÀ¸Øİq±¥¹•İ¥‘Ñ¡ô(€€€íq½±½Éí‘…É­É…åõq‰™Í•É¥•Íq1…É”(€€€€€q¥™Í¹…µ”ÍÕ‰Ñ¥Ñ±•q•¹‘Í¹…µ•qÍÕ‰Ñ¥Ñ±•qqlÉ•áuq™¥ô(€€€q½±½ÉíÉ…åõq¹½Éµ…±Í¥é”(€€€íqÉ•¹•İ½µµ…¹‘íq…ÉÉ…åÍÑÉ•Ñ¡õìÀ¸ØÄáô(€€€q‰•¥¹íÑ…‰Õ±…Éõí±ô(€€€€€€”q¥™Í¹…µ”…ÕÑ¡½Éq•¹‘Í¹…µ”q…ÕÑ¡½É¹…µ”q…ÕÑ¡½Éqqq™¤(€€€€€q¥™áq…ÕÑ¡½Éq•µÁÑåq•±Í•q…ÕÑ¡½É¹…µ•q¹½Éµ…±q…ÕÑ¡½Éqpq™¤(€€€€€q¥™Í¹…µ”¥¹ÍÑ¥ÑÕÑ•q•¹‘Í¹…µ”q¥¹ÍÑ¥ÑÕÑ•¹…µ”q¹½Éµ…±q¥¹ÍÑ¥ÑÕÑ•qpq™¤(€€€€€€”q¥™Í¹…µ”‘…Ñ•q•¹‘Í¹…µ”€q‘…Ñ•qqq™¤(€€€€€q¥™áq‘…Ñ•q•µÁÑåq•±Í•q‘…Ñ•¹…µ•q¹½Éµ…±q‘…Ñ”qpq™¤(€€€€€q¥™Í¹…µ”Ù•ÉÍ¥½¹q•¹‘Í¹…µ”q¹½Éµ…±qÙ•ÉÍ¥½¹¹…µ•qÙ•ÉÍ¥½¹qpq™¤(€€€€€q¥™Í¹…µ”‰¥½¥¹™½q•¹‘Í¹…µ”q¹½Éµ…±q‰¥½¥¹™½qpq™¤(€€€q•¹‘íÑ…‰Õ±…Éõô(€q•¹‘íµ¥¹¥Á…•ô(€q‰•¥¹íµ¥¹¥Á…•õmuìÀ¸Èİq±¥¹•İ¥‘Ñ¡ô(€q‰•¥¹íÑ¥­éÁ¥ÑÕÉ•õmÉ•µ•µ‰•ÈÁ¥ÑÕÉ”±½Ù•É±…åt(€€€q‰•¥¹íÁ™½¹±…å•Éõí‰…­É½Õ¹‘ô(€€€€€q¹½‘•m½Á…¥ÑäôÀ¸à°(€€€€€€€€€€€…¹¡½ÈõÍ½ÕÑ •…ÍĞ°(€€€€€€€€€€€½ÕÑ•ÈÍ•ÀôÁÁĞ°(€€€€€€€€€€€¥¹¹•ÈÍ•ÀôÁÁÑt…Ğ€ ¡ÕÉÉ•¹ĞÁ…”¹Í½ÕÑ •…ÍĞ¤€¬ ´Ä¸Á¥¸°È¸Õ¥¸¤¤ì(€€€€€€€€€€€€€q¥™Í¹…µ”±½½q•¹‘Í¹…µ•q¥¹±Õ‘•É…Á¡¥Ímİ¥‘Ñ ôÙµuíq±½½õq™¥ôì(€€€q•¹‘íÁ™½¹±…å•Éô(€q•¹‘íÑ¥­éÁ¥ÑÕÉ•ô(€q•¹‘íµ¥¹¥Á…•ô(€qÙ™¥±°(€q‰•¥¹í•¹Ñ•Éô(€€€qÍ•ÑÍÑÉ•Ñ¡ìÄ¸Íô(€€€qÁ…É‰½ámÑuìÀ¸İqÑ•áÑİ¥‘Ñ¡õíq•¹Ñ•É¥¹œq¥ÑÍ¡…Á”€(€€€€€q¥™Í¹…µ”•áÑÉ…¥¹™½q•¹‘Í¹…µ•q•áÑÉ…¥¹™½q™¥ô(€q•¹‘í•¹Ñ•Éô(€qÙ™¥±°)q•¹‘íÑ¥Ñ±•Á…•ô)qÉ•ÍÑ½É••½µ•ÑÉä)qÑ¡¥ÍÁ…•ÍÑå±•í•µÁÑåõô(()q¹•İ½µµ…¹‘íq‘½±±…Éõíqµ‰½áíqÑ•áÑ‘½±±…Éõô()qI•ÅÕ¥É•A…­…•í±¥ÍÑ¥¹Íô)qÉ•¹•İ½µµ…¹‘íqÑÑ‘•™…Õ±ÑõíµÑÑô)q±ÍÑ‘•™¥¹•ÍÑå±•íµåÍÑå±•õì(€‰…Í¥ÍÑå±”ô”(€€€qÑÑ™…µ¥±ä(€€€q±ÍÑ¥™‘¥ÍÁ±…åÍÑå±•qÍµ…±±q™¤)ô()q±ÍÑÍ•Ñí‰…Í¥ÍÑå±”õqÑÑ™…µ¥±ä±ÍÑå±”õµåÍÑå±”±‰É•…­±¥¹•ÌõÑÉÕ•ô()q‘•™¥¹•½±½Éí±¥¡ÑÉ•åõíÉ‰õìÀ¸ä°À¸ä°À¸åô)q‘•™¥¹•½±½Éí™É•¹¡Á±ÕµõíI	õìÄäÀ°ÈÀ°àÍô)q±ÍÑÍ•Ñí±…¹Õ…”õm1…Q•auQ•`°(€Ñ•áÍÍÑå±”ô©q½±½Éíİ¥¹•É•‘ô°(€¹Õµ‰•ÉÌõ¹½¹”°(€µ…Ñ¡•Í…Á”õ™…±Í”°(€‰É•…­±¥¹•ÌõÑÉÕ”°(€­•åİ½É‘ÍÑå±”õq½±½Éíİ¥¹•É•‘ô°(€½µµ•¹ÑÍÑå±”õq½±½ÉíÉ…åô°(€•µÁ õí•±•…¹ÑÁ…Á•È±™½¹Ñ•¹Œ±™½¹ÑÍÁ•Œ±á•),±¥Ñ•ÍÑå±”±¥É…5½¹¼±áÕ¹¥½‘”±™¥ÕÉ”±™¥œ±¥µ…”±¥µœ±Ñ…‰±”±¥Ñ•µ¥é”±•¹Õµ•É…Ñ”±Ñ•à±µ¥É½ÑåÁ”±‘•ÍÉ¥ÁÑ¥½¸±Ñ¥µ•Ì±‰½½­Ñ…‰Ì±Ñ…‰Õ±…È±A1…Q•`±a•1…Q•`±ÑåÁ”Å´±	¥‰Q•`±‘•Ù¥”±½±½È±µ½‘”±±…¹œ±…µÍÑ¡´±Ñ½±½É‰½à±Ñ¥Ñ±•ÍÑå±”±¥Ñ”±Ñ•à±±¥ÍÑ¥¹Ì±‰…Í”±µ…Ñ ±Í¡•µ”±Ñ½Œ±•Í¥¹Ğ±¡¥¹•Í•™½¹Ğ±…µÍµ…Ñ ±‰¥‰ÍÑå±”±¹…Ñ‰¥ˆ±Á™½É¹…µ•¹Ñô°(€•µÁ¡ÍÑå±”õíq½±½Éí™É•¹¡Á±Õµõô°(€µ½É•­•åİ½É‘Ìõí•±…É•Måµ‰½±½¹Ğ±M•ÑMåµ‰½±½¹Ğ±Ñ½ÁÉÕ±”±µ¥‘ÉÕ±”±‰½ÑÑ½µÉÕ±”±¥¹ÍÑ¥ÑÕÑ”±Ù•ÉÍ¥½¸±¥¹±Õ‘•É…Á¡¥Ì±Í•Ñµ…¥¹™½¹Ğ±Í•ÑÍ…¹Í™½¹Ğ±Í•Ñµ½¹½™½¹Ğ€±Í•Ñ)-µ…¥¹™½¹Ğ±Í•Ñ)-Í…¹Í™½¹Ğ±Í•Ñ)-µ½¹½™½¹Ğ±I•ÅÕ¥É•A…­…”±™¥É•˜±Ñ…‰É•˜±•µ…¥°±µ…­•Ñ¥Ñ±”±­•åİ½É‘Ì±‘•™¥¹•½±½È±•áÑÉ…¥¹™¼±±½¼±½Ù•È±ÍÕ‰Ñ¥Ñ±”±…ÁÁ•¹‘¥à±¡…ÁÑ•È±¡åÁ•ÉÍ•ÑÕÀ±µ…¥¹µ…ÑÑ•È±™É½¹Ñµ…ÑÑ•È±Ñ…‰±•½™½¹Ñ•¹ÑÌ±•±•…¹ÑÁ…È±¡•¥Ñ¤±­…¥Í¡Ô±±ÍÑÍ•Ğ±Á…•½±½È±é¡¹Õµ‰•È±µ…É¥¹Á…È±Á…ÉĞ±•ÅÕ½Ñ”±µ…É¥¹¹½Ñ”±‰¥½¥¹™¼±‘…Ñ•¡…¹”±±¥ÍÑ½™¡…¹”±±Ù•ÉĞ±±…ÍÑÁ…”±Í½¹Ñ¤±¡•¥Ñ¤±™…¹Í½¹œ±Í•Ñ)-™…µ¥±å™½¹Ğ±Ñ•áÑ‰™ô°(€™É…µ”õÍ¥¹±”°(€Ñ…‰Í¥é”ôÈ°(€ÉÕ±•½±½Èõq½±½ÉíÍÑÉÕÑÕÉ•½±½Éô°(€™É…µ•ÉÕ±”ôÀ¸ÉÁĞ°(€½±Õµ¹Ìõ™±•á¥‰±”°(€€”‰…­É½Õ¹‘½±½Èõq½±½Éí±¥¡ÑÉ•åô)ô()q¹•İ½µµ…¹‘q‰µµ…áìÁô)qI•ÅÕ¥É•A…­…•í‰µô((”…‘Ñ¡”±¥ÍĞ½˜¡…¹”¡¥ÍÑ½Éä)q¹•İ½µµ…¹‘íq‘…Ñ•¥¹™½±¥¹•õlÉuì(€q¹½¥¹‘•¹Ñqµ…­•‰½álÁÁÑumÉuì”(€qµ…­•‰½ál´Í•µumÉuì”(€€€qÍµ…±°(€€€qÑ•áÑ‰™íqÑ•áÑ½±½ÉíÍÑÉÕÑÕÉ•½±½ÉõìŒÅõõõpípíô”(€íq¥ÑÍ¡…Á•qÕÁ‘…Ñ•¹…µ•q¥¹½É•ÍÁ…•ÌŒÉõô()q¹•İ½µµ…¹‘íq‘…Ñ•¡…¹•õlÉuì”(€q¹½¥¹‘•¹Ñíqµ…­•‰½ámqÑ•áÑİ¥‘Ñ¡umÉuíq½±½ÉíÍÑÉÕÑÕÉ•½±½ÉõqÉÕ±•ìÄ¸ÄÕqÑ•áÑİ¥‘Ñ¡õì¸ÑÁÑõõô(€q‘…Ñ•¥¹™½±¥¹•ìŒÅõìŒÉô(€q…‘‘½¹Ñ•¹ÑÍ±¥¹•í‘…Ñ•ÍõíÍ•Ñ¥½¹õìŒÄ€´´€ŒÉõô()q¹•İ½µµ…¹‘íq±¥ÍÑ½™¡…¹•Íõì”(€q‰•¥¹É½ÕÀ(€€€qÉ•¹•İ½µµ…¹‘íq½¹Ñ•¹ÑÍ¹…µ•õíq¡¥ÍÑ½Éå¹…µ•ô(€€€q±•Ñq½±‘ÍÑ…ÉÑÑ½qÍÑ…ÉÑÑ½Œ(€€€q‘•™qÍÑ…ÉÑÑ½ŒŒŒÅì(€€€€€q½±‘ÍÑ…ÉÑÑ½í‘…Ñ•Íõô(€€€qÑ…‰±•½™½¹Ñ•¹ÑÌ”(€q•¹‘É½ÕÁô(”¡ÑÑÁÌè¼½Ñ•à¹ÍÑ…­•á¡…¹”¹½´½ÅÕ•ÍÑ¥½¹Ì¼ĞÜÈäÌÄ½±¥ÍĞµ½˜µ…±°µ‘…Ñ•Ìµ¥¸µ„µ‘½Õµ•¹Ğ()q¹•İ•¹Ù¥É½¹µ•¹Ñí¡…¹•õì(€q‰•¥¹í•¹Õµ•É…Ñ•õm±…‰•°õqÍµ…±±qÁÉ½Ñ•Ñq¥É±•‘íq…É…‰¥Œ©õuõì(€q•¹‘í•¹Õµ•É…Ñ•õô()q…‘‘‰¥‰É•Í½ÕÉ•m±½…Ñ¥½¸õ±½…±uíÉ•™•É•¹”¹‰¥‰ô()qÉ•¹•İ½µµ…¹‘qÑ…‰±•½™½¹Ñ•¹ÑÍì”(€q¡åÁ•ÉÍ•ÑÕÁí±¥¹­Ñ½Œõ…±°°±¥¹­½±½Èõ‰±…­ô(€€€q¥™Ñİ½½±Õµ¸(€€€€€qÉ•ÍÑ½¹•½±ÑÉÕ•q½¹•½±Õµ¸(€€€q•±Í”(€€€€€qÉ•ÍÑ½¹•½±™…±Í”(€€€q™¤(€€€q¡…ÁÑ•È©íq½¹Ñ•¹ÑÍ¹…µ”(€€€€€€€qµ­‰½Ñ¡ì”(€€€€€€€€€€q5…­•UÁÁ•É…Í•q½¹Ñ•¹ÑÍ¹…µ•õíq5…­•UÁÁ•É…Í•q½¹Ñ•¹ÑÍ¹…µ•õô”(€€€q¥™‘•™ÍÑÉ¥¹íq19QÑ½õíÑİ½½±õì(€€€€€qÍ•Ñ±•¹Ñ¡íq½±Õµ¹Í•ÁõìÉ•µô(€€€€€q‰•¥¹íµÕ±Ñ¥½±ÍõìÉô”(€€€€€€€qÍÑ…ÉÑÑ½íÑ½ô(€€€€€q•¹‘íµÕ±Ñ¥½±Íõõì(€€€€€qÍÑ…ÉÑÑ½íÑ½õô(€€€q¥™É•ÍÑ½¹•½±qÑİ½½±Õµ¹q™¤(€€€q¡åÁ•ÉÍ•ÑÕÁí±¥¹­½±½Èõİ¥¹•É•‘õô(()qÉ•¹•İ½µµ…¹©íq±•…É‘½Õ‰±•Á…•õíq±•…ÉÁ…•q¥™Ñİ½Í¥‘”q¥™½‘‘qÁ…•q•±Í”)q¡‰½áíô”)qÑ¡¥ÍÁ…•ÍÑå±•í•µÁÑåô”)q¹•İÁ…””)q¥™Ñİ½½±Õµ¹q¡‰½áíõq¹•İÁ…•q™¥q™¥q™¥ô(((”¡ÑÑÁÌè¼½Ñ•à¹ÍÑ…­•á¡…¹”¹½´½ÅÕ•ÍÑ¥½¹Ì¼ÔØàÌä½¡…ÁÑ•É¹…µ”µ¥ÌµÕÍ•µ•Ù•¸µ™½Èµ…ÁÁ•¹‘¥àµ¡…ÁÑ•ÉÌµ¥¸µÑ½Œ)qÕÍ•Á…­…•í…±ô)qÕÍ•Á…­…•mÑ¥Ñ±•ÍuíÑ½±½™Ñô)q¥™‘•™ÍÑÉ¥¹íq19Q±…¹õí¹õì(€qÉ•¹•İ½µµ…¹‘íq™Ñ¡…ÁÁÉ•Í¹Õµõíq‰•™½É•¡…ÁqÍÁ…•ô(€qÉ•¹•İ½µµ…¹‘íq™Ñ¡…Á…™Ñ•ÉÍ¹ÕµõíqÍÁ…•q…™Ñ•É¡…Áô(€qÍ•Ñ±•¹Ñ¡íq™Ñ¡…Á¹Õµİ¥‘Ñ¡õíqİ¥‘Ñ¡½™íqÑ•áÑ‰™ï¦f–öUøääåõõô(€q…‘‘Ñ½µ…É½q…ÁÁ•¹‘¥áì”(€€€q…‘‘Ñ½½¹Ñ•¹ÑÍíÑ½õì”(€€€€€qÁÉ½Ñ•ÑqÉ•¹•İ½µµ…¹‘íqÁÉ½Ñ•Ñq™Ñ¡…ÁÁÉ•Í¹Õµõíq…ÁÁ•¹‘¥á¹…µ•qÍÁ…•ô”(€€€€€qÁÉ½Ñ•ÑqÉ•¹•İ½µµ…¹‘íqÁÉ½Ñ•Ñq™Ñ¡…Á…™Ñ•ÉÍ¹Õµõíô”(€€€ô”(€ô)õì(€qÉ•¹•İ½µµ…¹‘íq™Ñ¡…ÁÁÉ•Í¹Õµõíq¡…ÁÑ•É¹…µ•qÍÁ…•ô(€qÉ•¹•İ½µµ…¹‘íq™Ñ¡…Á…™Ñ•ÉÍ¹ÕµõíqÍÁ…•ô(€qÍ•Ñ±•¹Ñ¡íq™Ñ¡…Á¹Õµİ¥‘Ñ¡õíqİ¥‘Ñ¡½™íqÑ•áÑ‰™íÁÁ•¹‘¥áøåõõô(€q…‘‘Ñ½µ…É½q…ÁÁ•¹‘¥áì”(€€€q…‘‘Ñ½½¹Ñ•¹ÑÍíÑ½õì”(€€€€€qÁÉ½Ñ•ÑqÉ•¹•İ½µµ…¹‘íqÁÉ½Ñ•Ñq™Ñ¡…ÁÁÉ•Í¹Õµõíq…ÁÁ•¹‘¥á¹…µ•qÍÁ…•ô”(€€€€€qÁÉ½Ñ•ÑqÉ•¹•İ½µµ…¹‘íqÁÉ½Ñ•Ñq™Ñ¡…Á…™Ñ•ÉÍ¹Õµõíô”(€€€€€qÍ•Ñ±•¹Ñ¡íq™Ñ¡…Á¹Õµİ¥‘Ñ¡õíqİ¥‘Ñ¡½™íqÑ•áÑ‰™íÁÁ•¹‘¥áøääåõõô(€€€ô”(€ô)ô((”É•ÍÑ½É”Ñ¡”ÑĞ‘•™…Õ±Ğ™…µ¥±äÑ¼±µ½‘•É¸ÑĞ™…µ¥±ä)qÉ•¹•İ½µµ…¹‘qÑÑ‘•™…Õ±Ñí±µÑÑ