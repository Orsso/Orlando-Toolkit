<?xml version="1.0" encoding="UTF-8"?>
<!-- ============================================================= -->
<!--                    HEADER                                     -->
<!-- ============================================================= -->
<!--  MODULE:    Orlando Action Domain                            -->
<!--  VERSION:   1.3                                               -->
<!--  DATE:      March 2021                                        -->
<!--                                                               -->
<!-- ============================================================= -->
<!-- ============================================================= -->
<!--                    PUBLIC DOCUMENT TYPE DEFINITION            -->
<!--                    TYPICAL INVOCATION                         -->
<!--                                                               -->
<!--  Refer to this file by the following public identifier or an  -->
<!--       appropriate system identifier                           -->
<!--     PUBLIC "-//OASIS//ELEMENTS Orlando Action Domain//EN"     -->
<!--       Delivered as file "sp-act-d.mod"                        -->
<!-- ============================================================= -->
<!-- SYSTEM:     Darwin Information Typing Architecture (DITA)     -->
<!--                                                               -->
<!-- PURPOSE:    Define elements and specialization atttributes    -->
<!--             for Orlando Action Domain                             -->
<!--                                                               -->
<!-- ORIGINAL CREATION DATE:                                       -->
<!--             March 2021                                        -->
<!--                                                               -->
<!--             (C) Copyright 2021, Orlando Corp.                    -->
<!--             All Rights Reserved.                              -->
<!--  AUTHOR:    Glenn Emerson, gemerson@Orlando.com              -->
<!--                                                               -->
<!--  UPDATES: 2021.03.05 Creation date                            -->
<!--           2021.03.12 Renamed act to action, chalge to         -->
<!--                      challenge. Removed actext, landasap      -->
<!--                      Added note to challenge and response     -->
<!-- ============================================================= -->

<!-- ============================================================= -->
<!--                   ELEMENT NAME ENTITIES                       -->
<!-- ============================================================= -->

<!ENTITY % action        "action"                                    >
<!ENTITY % challenge     "challenge"                                 >
<!ENTITY % response      "response"                                  >
<!ENTITY % comment       "comment"                                   >

<!-- ============================================================= -->
<!--                    ELEMENT DECLARATIONS                       -->
<!-- ============================================================= -->


<!--                    LONG NAME: Action           -->
<!ENTITY % action.content
                       "((%title;)?, (%challenge; , %response;),
                         (%comment;)?)"
>
<!ENTITY % action.attributes
              "%univ-atts;
               outputclass
                          CDATA
                                    #IMPLIED"
>
<!ELEMENT  action %action.content;>
<!ATTLIST  action %action.attributes;>

<!--                    LONG NAME: Challenge           -->
<!ENTITY % challenge.content
                       "(#PCDATA | %p; | %fn; | %keyword; | %ph; | %note;)*"
>
<!ENTITY % challenge.attributes
              "%univ-atts;
               outputclass
                          CDATA
                                    #IMPLIED"
>
<!ELEMENT  challenge %challenge.content;>
<!ATTLIST  challenge %challenge.attributes;>

<!--                    LONG NAME: Response           -->
<!ENTITY % response.content
                       "(#PCDATA | %p; | %fn; | %keyword; | %ph; | %note;)*"
>
<!ENTITY % response.attributes
              "%univ-atts;
               outputclass
                          CDATA
                                    #IMPLIED"
>
<!ELEMENT  response %response.content;>
<!ATTLIST  response %response.attributes;>



<!--                    LONG NAME: Comment           -->
<!ENTITY % comment.content
                       "(#PCDATA | %p; | %note; | %fn; | %keyword; | %ph;)*"
>
<!ENTITY % comment.attributes
              "%univ-atts;
               outputclass
                          CDATA
                                    #IMPLIED"
>
<!ELEMENT  comment %comment.content;>
<!ATTLIST  comment %comment.attributes;>




<!-- ============================================================= -->
<!--             SPECIALIZATION ATTRIBUTE DECLARATIONS             -->
<!-- ============================================================= -->
<!ATTLIST  action         %global-atts;  class CDATA "- topic/p act-d/action ">
<!ATTLIST  challenge      %global-atts;  class CDATA "- topic/p act-d/challenge ">
<!ATTLIST  response       %global-atts;  class CDATA "- topic/p act-d/response ">
<!ATTLIST  comment        %global-atts;  class CDATA "- topic/p act-d/comment ">


<!-- ================== End of DITA Concept ==================== -->
 