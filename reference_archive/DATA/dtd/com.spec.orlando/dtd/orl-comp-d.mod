<?xml version="1.0" encoding="UTF-8"?>
<!-- ============================================================= -->
<!--                    HEADER                                     -->
<!-- ============================================================= -->
<!--  MODULE:    Orlando Compliance Domain                     -->
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
<!-- PUBLIC "-//OASIS//ELEMENTS Orlando Compliance Domain//EN"  -->
<!--       Delivered as file "sp-comp-d.mod"                       -->
<!-- ============================================================= -->
<!-- SYSTEM:     Darwin Information Typing Architecture (DITA)     -->
<!--                                                               -->
<!-- PURPOSE:    Define elements and specialization atttributes    -->
<!--             for Orlando Compliance Domain                      -->
<!--                                                               -->
<!-- ORIGINAL CREATION DATE:                                       -->
<!--             March 2021                                        -->
<!--                                                               -->
<!--             (C) Copyright 2021, Orlando Corp.                    -->
<!--             All Rights Reserved.                              -->
<!--  AUTHOR:    Glenn Emerson, gemerson@Orlando.com              -->
<!--                                                               -->
<!--  UPDATES: 2021.03.05 Creation date                            -->
<!-- ============================================================= -->

<!-- ============================================================= -->
<!--                   ELEMENT NAME ENTITIES                       -->
<!-- ============================================================= -->

<!ENTITY % compliance           "compliance"                         > 

<!-- ============================================================= -->
<!--                    ELEMENT DECLARATIONS                       -->
<!-- ============================================================= -->


<!--                    LONG NAME: Compliance           -->
<!ENTITY % compliance.content
                       "(#PCDATA)*"
>
<!ENTITY % compliance.attributes
              "%univ-atts;
               regtype
                          (far|sfar|cfr|sai|srr|opspec|isarp|carops|jarops|euops|atos|tc|miscreg)
                                    #REQUIRED
               keyref
                          CDATA
                                    #IMPLIED
               outputclass
                          CDATA
                                    #IMPLIED"
>
<!ELEMENT  compliance %compliance.content;>
<!ATTLIST  compliance %compliance.attributes;>



<!-- ============================================================= -->
<!--             SPECIALIZATION ATTRIBUTE DECLARATIONS             -->
<!-- ============================================================= -->
<!ATTLIST  compliance     %global-atts;  class CDATA "+ topic/keyword comp-d/compliance ">

<!-- ================== End of DITA Concept ==================== -->
 